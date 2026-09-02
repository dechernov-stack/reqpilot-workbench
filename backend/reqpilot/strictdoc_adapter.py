"""Native StrictDoc JSON adapter and project revision calculation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, Final

from filelock import FileLock

from reqpilot.config import ProjectConfig
from reqpilot.errors import NotFoundError, PathSecurityError, ReqPilotError, StrictDocCommandError
from reqpilot.models import (
    Diagnostic,
    DiagnosticSeverity,
    NativeCommandResult,
    Relation,
    Requirement,
    RequirementList,
    ValidationResult,
)

PINNED_STRICTDOC_VERSION: Final = "0.29.0"
STRICTDOC_ENTRYPOINT: Final = "from strictdoc.cli.main import main; main()"
KNOWN_FIELDS: Final = {
    "MID",
    "UID",
    "TYPE",
    "STATUS",
    "PRIORITY",
    "VERIFICATION_METHOD",
    "OWNER",
    "SOURCE",
    "TAGS",
    "TITLE",
    "STATEMENT",
    "RATIONALE",
    "ACCEPTANCE_CRITERIA",
    "COMMENT",
    "RELATIONS",
}

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


def sha256_file(path: Path) -> str:
    """Calculate a streaming SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iter_native_requirements(
    value: Any,
    section_path: tuple[str, ...] = (),
) -> Iterator[tuple[dict[str, Any], tuple[str, ...]]]:
    """Yield native requirement dictionaries with their section-title ancestry."""

    if isinstance(value, dict):
        node_type = value.get("_NODE_TYPE")
        current_path = section_path
        if node_type == "SECTION":
            title = _clean_text(value.get("TITLE"))
            if title:
                current_path = (*section_path, title)
        if node_type == "REQUIREMENT":
            yield value, current_path
            return
        for nested in value.values():
            yield from _iter_native_requirements(nested, current_path)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_native_requirements(nested, section_path)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    return value


class StrictDocAdapter:
    """Read canonical `.sdoc` files only through StrictDoc's JSON exporter."""

    def __init__(
        self,
        config: ProjectConfig,
        *,
        python_executable: str | None = None,
        runner: ProcessRunner = subprocess.run,
        timeout_seconds: float = 120,
    ) -> None:
        self.config = config
        self.python_executable = python_executable or sys.executable
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        state_dir = config.ensure_state_dir()
        self.lock = FileLock(str(state_dir / "strictdoc.lock"), timeout=30)
        self.cache_path = config.ensure_state_dir("cache") / "strictdoc-index.json"
        self._requirements: tuple[Requirement, ...] = ()
        self._revision: str | None = None
        self._last_command: NativeCommandResult | None = None
        self._last_diagnostics: list[Diagnostic] = []
        self._last_refresh_epoch: float | None = None

    @property
    def command_prefix(self) -> list[str]:
        """Return the exact native StrictDoc CLI command prefix."""

        return [self.python_executable, "-c", STRICTDOC_ENTRYPOINT]

    @property
    def version(self) -> str:
        """Return the installed StrictDoc distribution version."""

        return importlib.metadata.version("strictdoc")

    @property
    def revision(self) -> str:
        """Return the cached revision, loading the native index when needed."""

        if self._revision is None:
            self.refresh()
        assert self._revision is not None
        return self._revision

    @property
    def diagnostics(self) -> list[Diagnostic]:
        """Return diagnostics from the latest adapter operation."""

        return list(self._last_diagnostics)

    @property
    def last_command(self) -> NativeCommandResult | None:
        """Return metadata for the latest StrictDoc process."""

        return self._last_command

    @property
    def last_refresh_epoch(self) -> float | None:
        """Return the UNIX timestamp of the latest successful refresh."""

        return self._last_refresh_epoch

    def calculate_revision(self, requirements_dir: Path | None = None) -> str:
        """Hash canonical sources plus persistent deleted-UID safety metadata."""

        selected_root = requirements_dir or self.config.requirements_dir
        source_root = self.assert_safe_requirements_tree(selected_root)
        canonical_root = self.config.requirements_dir.resolve()
        configured_files = [
            path.relative_to(canonical_root) for path in self.config.managed_document_paths
        ]
        extra_files = [
            path.relative_to(canonical_root)
            for path in canonical_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".sgra", ".py", ".css", ".svg"}
            and "__pycache__" not in path.parts
        ]
        digest = hashlib.sha256()
        for relative in sorted(
            set(configured_files + extra_files), key=lambda item: item.as_posix()
        ):
            path = source_root / relative
            if not path.is_file():
                digest.update(f"missing:{relative.as_posix()}\0".encode())
                continue
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            digest.update(b"\0")
        if requirements_dir is None:
            tombstones = self.config.deleted_uid_registry_path
            digest.update(self.config.strictdoc.deleted_uids.encode("utf-8"))
            digest.update(b"\0")
            if tombstones.is_file():
                digest.update(tombstones.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def run_native_export(
        self,
        requirements_dir: Path,
        output_dir: Path,
        *,
        export_format: str,
        extra_args: Sequence[str] = (),
    ) -> NativeCommandResult:
        """Invoke StrictDoc with a list of arguments and `shell=False`."""

        requirements_dir = self.assert_safe_requirements_tree(requirements_dir)
        config_relative = self.config.strictdoc_config_path.relative_to(
            self.config.requirements_dir
        )
        command = [
            *self.command_prefix,
            "export",
            str(requirements_dir),
            "--config",
            str(requirements_dir / config_relative),
            "--output-dir",
            str(output_dir),
            f"--formats={export_format}",
            "--no-parallelization",
            *extra_args,
        ]
        started = time.monotonic()
        process_environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
        }
        executable_dir = str(Path(self.python_executable).absolute().parent)
        inherited_path = process_environment.get("PATH", "")
        process_environment["PATH"] = (
            executable_dir if not inherited_path else executable_dir + os.pathsep + inherited_path
        )
        try:
            completed = self.runner(
                command,
                cwd=self.config.repo_root,
                check=False,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
                env=process_environment,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            result = NativeCommandResult(
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout[-100_000:],
                stderr=completed.stderr[-100_000:],
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as error:
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout = error.stdout if isinstance(error.stdout, str) else ""
            stderr = error.stderr if isinstance(error.stderr, str) else ""
            result = NativeCommandResult(
                command=command,
                returncode=124,
                stdout=stdout[-100_000:],
                stderr=(stderr + f"\nStrictDoc timed out after {self.timeout_seconds}s")[-100_000:],
                duration_ms=duration_ms,
            )
        except OSError as error:
            result = NativeCommandResult(
                command=command,
                returncode=127,
                stdout="",
                stderr=f"StrictDoc process could not be started: {error}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        self._last_command = result
        return result

    def assert_safe_requirements_tree(self, requirements_dir: Path) -> Path:
        """Reject source trees containing symlinks or repository escapes."""

        repo_root = self.config.repo_root.resolve(strict=True)
        lexical_root = Path(os.path.abspath(requirements_dir))
        try:
            relative_root = lexical_root.relative_to(repo_root)
        except ValueError as error:
            raise PathSecurityError(
                "StrictDoc source tree must remain inside the repository."
            ) from error
        cursor = repo_root
        for part in relative_root.parts:
            cursor /= part
            if cursor.is_symlink():
                raise PathSecurityError(f"StrictDoc source tree contains a symlink: {cursor}.")
        try:
            root = lexical_root.resolve(strict=True)
            root.relative_to(repo_root)
        except (OSError, ValueError) as error:
            raise PathSecurityError("StrictDoc source tree is missing or unsafe.") from error
        if not root.is_dir():
            raise PathSecurityError("StrictDoc source root is not a directory.")
        for current_name, directory_names, file_names in os.walk(
            root, topdown=True, followlinks=False
        ):
            current = Path(current_name)
            for name in [*directory_names, *file_names]:
                candidate = current / name
                if candidate.is_symlink():
                    raise PathSecurityError(
                        f"StrictDoc source tree contains a symlink: {candidate}."
                    )
                try:
                    candidate.resolve(strict=True).relative_to(root)
                except (OSError, ValueError) as error:
                    raise PathSecurityError(
                        f"StrictDoc source path is missing or escapes the tree: {candidate}."
                    ) from error
        return root

    def refresh(self) -> RequirementList:
        """Rebuild the derived requirement index under the project lock."""

        with self.lock:
            return self.refresh_locked()

    def refresh_locked(self) -> RequirementList:
        """Rebuild the derived index while the caller already owns the lock."""

        payload, revision, command, diagnostics = self._read_native_snapshot()
        if command.returncode != 0 or payload is None:
            self._last_diagnostics = diagnostics
            raise StrictDocCommandError(
                "Native StrictDoc JSON export failed.",
                [item.model_dump(mode="json") for item in diagnostics],
            )
        return self._accept_snapshot(payload, revision, diagnostics)

    def _accept_snapshot(
        self,
        payload: Any,
        revision: str,
        diagnostics: list[Diagnostic],
    ) -> RequirementList:
        """Normalize and cache one payload/revision pair captured atomically."""

        requirements = self.normalize_payload(payload, revision=revision)
        self._requirements = tuple(requirements)
        self._revision = revision
        self._last_diagnostics = diagnostics
        self._last_refresh_epoch = time.time()
        self._write_cache(payload=payload, revision=revision)
        return RequirementList(items=requirements, total=len(requirements), revision=revision)

    def _read_native_snapshot(
        self,
    ) -> tuple[Any | None, str, NativeCommandResult, list[Diagnostic]]:
        """Read a source-consistent native JSON snapshot, retrying one changed read."""

        for attempt in range(2):
            revision_before = self.calculate_revision()
            with tempfile.TemporaryDirectory(prefix="reqpilot-json-") as temp_name:
                output_dir = Path(temp_name)
                command = self.run_native_export(
                    self.config.requirements_dir,
                    output_dir,
                    export_format="json",
                )
                diagnostics = self.command_diagnostics(command)
                payload: Any | None = None
                if command.returncode == 0:
                    json_path = output_dir / "json" / "index.json"
                    if not json_path.is_file():
                        diagnostics.append(
                            Diagnostic(
                                severity=DiagnosticSeverity.ERROR,
                                source="strictdoc",
                                code="missing_export",
                                message=f"StrictDoc did not create {json_path}.",
                            )
                        )
                        self._last_diagnostics = diagnostics
                        raise StrictDocCommandError(
                            "Native StrictDoc JSON artifact is missing.",
                            [item.model_dump(mode="json") for item in diagnostics],
                        )
                    try:
                        payload = json.loads(json_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as error:
                        diagnostics.append(
                            Diagnostic(
                                severity=DiagnosticSeverity.ERROR,
                                source="strictdoc-json",
                                code="invalid_json",
                                message=str(error),
                            )
                        )
                        self._last_diagnostics = diagnostics
                        raise StrictDocCommandError(
                            "Native StrictDoc JSON could not be read.",
                            [item.model_dump(mode="json") for item in diagnostics],
                        ) from error
            revision_after = self.calculate_revision()
            if revision_before == revision_after:
                return payload, revision_before, command, diagnostics
            changed = Diagnostic(
                severity=DiagnosticSeverity.ERROR,
                source="strictdoc",
                code="source_changed_during_read",
                message="Canonical StrictDoc sources changed during native JSON export.",
                details={
                    "revision_before": revision_before,
                    "revision_after": revision_after,
                    "attempt": attempt + 1,
                },
            )
            self._last_diagnostics = [*diagnostics, changed]
            if attempt == 1:
                raise ReqPilotError(
                    "source_changed_during_read",
                    "Canonical StrictDoc sources kept changing during native JSON export.",
                    409,
                    [item.model_dump(mode="json") for item in self._last_diagnostics],
                )
        raise AssertionError("unreachable")

    def list_requirements(
        self,
        *,
        text: str | None = None,
        status: str | None = None,
        type_: str | None = None,
        document: str | None = None,
    ) -> RequirementList:
        """List requirements with deterministic, case-insensitive filters."""

        current_revision = self.calculate_revision()
        if self._revision != current_revision:
            self.refresh()
        normalized_text = text.casefold().strip() if text else None
        items: list[Requirement] = []
        for item in self._requirements:
            if status and item.status != status:
                continue
            if type_ and item.type != type_:
                continue
            if document and document not in {item.document, Path(item.document).name}:
                continue
            if normalized_text:
                searchable = " ".join(
                    part
                    for part in [item.uid, item.title, item.statement, item.owner]
                    if part is not None
                ).casefold()
                if normalized_text not in searchable:
                    continue
            items.append(item)
        return RequirementList(items=items, total=len(items), revision=self.revision)

    def get_requirement(self, uid: str) -> Requirement:
        """Return one requirement by stable UID."""

        listing = self.list_requirements()
        for item in listing.items:
            if item.uid == uid:
                return item
        raise NotFoundError("Requirement", uid)

    def validate(self) -> ValidationResult:
        """Run the complete native StrictDoc JSON export validation pipeline."""

        with self.lock:
            payload, revision, result, diagnostics = self._read_native_snapshot()
            if result.returncode == 0 and payload is not None:
                self._accept_snapshot(payload, revision, diagnostics)
            else:
                self._last_diagnostics = diagnostics
            return ValidationResult(
                valid=result.returncode == 0,
                revision=revision,
                diagnostics=diagnostics,
                duration_ms=result.duration_ms,
            )

    def normalize_payload(self, payload: Any, *, revision: str) -> list[Requirement]:
        """Normalize StrictDoc's native JSON without turning it into a write model."""

        if not isinstance(payload, dict) or not isinstance(payload.get("DOCUMENTS"), list):
            raise StrictDocCommandError(
                "Native StrictDoc JSON has no DOCUMENTS array.",
                [
                    Diagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        source="strictdoc-json",
                        code="invalid_shape",
                        message="Expected an object containing DOCUMENTS array.",
                    ).model_dump(mode="json")
                ],
            )
        documents: list[Any] = payload["DOCUMENTS"]
        managed = list(self.config.managed_document_paths)
        if len(documents) != len(managed):
            raise StrictDocCommandError(
                "StrictDoc document count differs from the managed allowlist.",
                [
                    Diagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        source="strictdoc-json",
                        code="document_count_mismatch",
                        message=f"Native={len(documents)}, managed={len(managed)}.",
                    ).model_dump(mode="json")
                ],
            )
        managed_by_mid = self.config.managed_documents_by_mid

        mapped_documents: list[tuple[dict[str, Any], Path]] = []
        seen_document_mids: set[str] = set()
        for document_value in documents:
            if not isinstance(document_value, dict):
                raise StrictDocCommandError("Native StrictDoc document is not an object.", [])
            native_mid = _clean_text(document_value.get("MID"))
            if not native_mid:
                raise StrictDocCommandError("A native StrictDoc document lacks a stable MID.", [])
            document_mid: str = native_mid
            if document_mid in seen_document_mids:
                raise StrictDocCommandError(
                    f"Duplicate native StrictDoc document MID: {document_mid}.", []
                )
            seen_document_mids.add(document_mid)
            mapped_path = managed_by_mid.get(document_mid)
            if mapped_path is None:
                raise StrictDocCommandError(
                    f"Native StrictDoc document MID is not managed: {document_mid}.", []
                )
            document_path: Path = mapped_path
            mapped_documents.append((document_value, document_path))
        missing_document_mids = set(managed_by_mid) - seen_document_mids
        if missing_document_mids:
            missing = ", ".join(sorted(missing_document_mids))
            raise StrictDocCommandError(
                f"Managed StrictDoc document MIDs missing from native JSON: {missing}.", []
            )

        requirements: list[Requirement] = []
        seen_uids: set[str] = set()
        seen_mids: set[str] = set()
        for document_value, document_path in mapped_documents:
            document_title = str(document_value.get("TITLE", ""))
            relative_document = document_path.relative_to(self.config.repo_root).as_posix()
            for node, section_path in _iter_native_requirements(document_value.get("NODES", [])):
                uid = _clean_text(node.get("UID"))
                mid = _clean_text(node.get("MID"))
                if not uid or not mid:
                    raise StrictDocCommandError(
                        "A native requirement lacks stable UID or MID.",
                        [],
                    )
                if uid in seen_uids or mid in seen_mids:
                    raise StrictDocCommandError(
                        f"Duplicate UID or MID in native StrictDoc JSON: {uid}/{mid}.",
                        [],
                    )
                seen_uids.add(uid)
                seen_mids.add(mid)
                relation_values = node.get("RELATIONS", [])
                if not isinstance(relation_values, list):
                    raise StrictDocCommandError(f"RELATIONS is not an array for {uid}.", [])
                relations = [
                    Relation.model_validate(
                        {
                            "type": relation.get("TYPE", "Parent"),
                            "value": relation.get("VALUE", ""),
                            "role": relation.get("ROLE"),
                        }
                    )
                    for relation in relation_values
                    if isinstance(relation, dict)
                ]
                raw_tags = _clean_text(node.get("TAGS")) or ""
                tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
                extra_fields = {
                    key: value
                    for key, value in node.items()
                    if not key.startswith("_") and key not in KNOWN_FIELDS
                }
                requirements.append(
                    Requirement.model_validate(
                        {
                            "uid": uid,
                            "mid": mid,
                            "document": relative_document,
                            "document_path": relative_document,
                            "section_path": list(section_path),
                            "document_title": document_title,
                            "node_type": str(node.get("_NODE_TYPE", "REQUIREMENT")),
                            "toc": _clean_text(node.get("_TOC")),
                            "type": _clean_text(node.get("TYPE")),
                            "status": _clean_text(node.get("STATUS")),
                            "priority": _clean_text(node.get("PRIORITY")),
                            "verification_method": _clean_text(node.get("VERIFICATION_METHOD")),
                            "owner": _clean_text(node.get("OWNER")),
                            "source": _clean_text(node.get("SOURCE")),
                            "tags": tags,
                            "title": _clean_text(node.get("TITLE")),
                            "statement": _clean_text(node.get("STATEMENT")),
                            "rationale": _clean_text(node.get("RATIONALE")),
                            "acceptance_criteria": _clean_text(node.get("ACCEPTANCE_CRITERIA")),
                            "comment": _clean_text(node.get("COMMENT")),
                            "relations": relations,
                            "extra_fields": extra_fields,
                            "revision": revision,
                        }
                    )
                )
        return requirements

    def command_diagnostics(self, result: NativeCommandResult) -> list[Diagnostic]:
        """Convert process output to a compact structured diagnostic list."""

        diagnostics: list[Diagnostic] = []
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "StrictDoc failed."
            diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    source="strictdoc",
                    code="nonzero_exit",
                    message=message[-20_000:],
                    details={
                        "returncode": result.returncode,
                        "duration_ms": result.duration_ms,
                        "command": result.command,
                    },
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.INFO,
                    source="strictdoc",
                    code="native_export_ok",
                    message="Native StrictDoc export and semantic validation succeeded.",
                    details={"duration_ms": result.duration_ms},
                )
            )
        return diagnostics

    def _write_cache(self, *, payload: dict[str, Any], revision: str) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_value = {"revision": revision, "native": payload}
        temporary = self.cache_path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(cache_value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.cache_path)
