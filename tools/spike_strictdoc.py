#!/usr/bin/env python3
"""Prove StrictDoc 0.29.0 read/write compatibility without touching sources.

The spike deliberately uses StrictDoc's native JSON exporter for reads and
validation, and its parser/model/writer API for the mutation.  Every write is
made below a temporary directory.  A failed candidate is validated in a
disposable project copy, which models the pre-commit validation step of the
production writer.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.writer import SDWriter
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.core.traceability_index_builder import TraceabilityIndexBuilder
from strictdoc.helpers.parallelizer import Parallelizer

PINNED_STRICTDOC_VERSION = "0.29.0"
TARGET_UID = "SYS-002"
STRICTDOC_CLI_ENTRYPOINT = "from strictdoc.cli.main import main; main()"
MUTATED_RATIONALE = (
    "Совместимость записи подтверждена: инженерная проверка № 0.\n"
    "Строка Unicode: насос ⚙, давление Δp, русский текст.\n"
    "Финальная строка сохраняется без потери данных.\n"
)
SOURCE_SUFFIXES = {".css", ".py", ".sdoc", ".sgra", ".svg"}


class SpikeFailure(RuntimeError):
    """Raised when a compatibility invariant is not satisfied."""


@dataclass(frozen=True)
class ExportResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    payload: dict[str, Any] | None


@dataclass(frozen=True)
class ProjectSnapshot:
    documents: dict[str, dict[str, Any]]
    document_order: tuple[tuple[str, tuple[str, ...]], ...]
    nodes: dict[str, dict[str, Any]]

    @property
    def relation_count(self) -> int:
        return sum(len(node.get("RELATIONS", [])) for node in self.nodes.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="ReqPilot repository root (default: inferred from this script)",
    )
    return parser.parse_args()


def source_files(requirements_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in requirements_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix in SOURCE_SUFFIXES
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_manifest(requirements_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(requirements_dir).as_posix(): sha256_file(path)
        for path in source_files(requirements_dir)
    }


def manifest_digest(manifest: dict[str, str]) -> str:
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def strictdoc_command_prefix() -> tuple[str, ...]:
    """Return the installed StrictDoc console entry point as a subprocess command.

    Calling the package's registered ``strictdoc.cli.main:main`` entry point
    through the active interpreter is semantically identical to its generated
    console-script shim and remains usable in File Provider-backed workspaces
    where that tiny generated shim can be evicted independently.
    """

    return (sys.executable, "-c", STRICTDOC_CLI_ENTRYPOINT)


def run_process(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed executable and an argument list; shell is disabled.
        command,
        cwd=cwd,
        check=False,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def assert_exact_version(command_prefix: tuple[str, ...], *, cwd: Path) -> None:
    package_version = importlib.metadata.version("strictdoc")
    version_result = run_process([*command_prefix, "--version"], cwd=cwd)
    cli_version = version_result.stdout.strip()
    if version_result.returncode != 0:
        raise SpikeFailure(
            f"StrictDoc version command failed:\n{version_result.stdout}\n{version_result.stderr}"
        )
    if package_version != PINNED_STRICTDOC_VERSION or cli_version != PINNED_STRICTDOC_VERSION:
        raise SpikeFailure(
            "StrictDoc version mismatch: "
            f"package={package_version!r}, CLI={cli_version!r}, "
            f"required={PINNED_STRICTDOC_VERSION!r}."
        )


def native_json_export(
    command_prefix: tuple[str, ...],
    requirements_dir: Path,
    output_dir: Path,
    *,
    cwd: Path,
) -> ExportResult:
    command = [
        *command_prefix,
        "export",
        str(requirements_dir),
        "--config",
        str(requirements_dir / "strictdoc_config.py"),
        "--output-dir",
        str(output_dir),
        "--formats=json",
        "--no-parallelization",
    ]
    result = run_process(command, cwd=cwd)
    json_path = output_dir / "json" / "index.json"
    payload: dict[str, Any] | None = None
    if result.returncode == 0:
        if not json_path.is_file():
            raise SpikeFailure(f"Native export succeeded but did not create {json_path}.")
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise SpikeFailure("StrictDoc JSON root is not an object.")
        payload = loaded
    return ExportResult(
        command=tuple(command),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        payload=payload,
    )


def require_success(result: ExportResult, *, phase: str) -> dict[str, Any]:
    if result.returncode != 0 or result.payload is None:
        raise SpikeFailure(
            f"{phase} failed with exit code {result.returncode}.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.payload


def iter_requirement_nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("_NODE_TYPE") == "REQUIREMENT":
            yield value
            return
        for nested in value.values():
            yield from iter_requirement_nodes(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_requirement_nodes(nested)


def snapshot(payload: dict[str, Any]) -> ProjectSnapshot:
    documents_value = payload.get("DOCUMENTS")
    if not isinstance(documents_value, list):
        raise SpikeFailure("StrictDoc JSON does not contain a DOCUMENTS list.")

    documents: dict[str, dict[str, Any]] = {}
    document_order: list[tuple[str, tuple[str, ...]]] = []
    nodes: dict[str, dict[str, Any]] = {}

    for document_value in documents_value:
        if not isinstance(document_value, dict):
            raise SpikeFailure("StrictDoc JSON contains a non-object document.")
        document_mid = document_value.get("MID")
        if not isinstance(document_mid, str) or not document_mid:
            raise SpikeFailure("A StrictDoc JSON document has no stable MID.")
        if document_mid in documents:
            raise SpikeFailure(f"Duplicate document MID: {document_mid}.")

        document_metadata = {
            key: value
            for key, value in document_value.items()
            if key != "NODES" and not key.startswith("_")
        }
        documents[document_mid] = document_metadata

        document_uids: list[str] = []
        for node in iter_requirement_nodes(document_value.get("NODES", [])):
            uid = node.get("UID")
            mid = node.get("MID")
            if not isinstance(uid, str) or not uid:
                raise SpikeFailure("A requirement in native JSON has no UID.")
            if not isinstance(mid, str) or not mid:
                raise SpikeFailure(f"Requirement {uid} has no MID.")
            if uid in nodes:
                raise SpikeFailure(f"Duplicate requirement UID: {uid}.")
            nodes[uid] = {key: value for key, value in node.items() if not key.startswith("_")}
            document_uids.append(uid)
        document_order.append((document_mid, tuple(document_uids)))

    return ProjectSnapshot(
        documents=documents,
        document_order=tuple(document_order),
        nodes=nodes,
    )


def create_model_candidates(requirements_dir: Path, work_dir: Path) -> tuple[Path, Path, str]:
    project_config = ProjectConfigLoader.load(
        str(requirements_dir),
        output_dir=str(work_dir / "model-api-output"),
    )
    parser_log = io.StringIO()
    with redirect_stdout(parser_log):
        traceability_index = TraceabilityIndexBuilder.create(
            project_config=project_config,
            parallelizer=Parallelizer.create(False),
            skip_source_files=True,
        )

    matches: list[tuple[Any, SDocNode]] = []
    for document in traceability_index.document_tree.document_list:
        for node, _ in SDocDocumentIterator(document).all_content():
            if isinstance(node, SDocNode) and node.reserved_uid == TARGET_UID:
                matches.append((document, node))
    if len(matches) != 1:
        raise SpikeFailure(f"Expected one {TARGET_UID} node, found {len(matches)}.")

    document, node = matches[0]
    if document.meta is None:
        raise SpikeFailure(f"Document containing {TARGET_UID} has no path metadata.")
    source_path = Path(document.meta.input_doc_full_path)
    relative_path = source_path.relative_to(requirements_dir)

    node.set_field_value(
        field_name="RATIONALE",
        form_field_index=0,
        value=MUTATED_RATIONALE,
    )
    writer = SDWriter(project_config)
    valid_content = writer.write(document)
    if MUTATED_RATIONALE.rstrip("\n") not in valid_content:
        raise SpikeFailure("StrictDoc writer did not retain the Unicode multiline mutation.")

    candidates_dir = work_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    valid_candidate = candidates_dir / "valid.sdoc"
    valid_candidate.write_text(valid_content, encoding="utf-8")

    node.set_field_value(field_name="UID", form_field_index=0, value=None)
    invalid_content = writer.write(document)
    invalid_candidate = candidates_dir / "invalid-missing-uid.sdoc"
    invalid_candidate.write_text(invalid_content, encoding="utf-8")

    if f"UID: {TARGET_UID}" in invalid_content:
        raise SpikeFailure("The intentionally invalid candidate still contains its UID.")
    return valid_candidate, invalid_candidate, relative_path.as_posix()


def disposable_project_with_candidate(
    pristine_requirements: Path,
    candidate: Path,
    relative_target: str,
    destination: Path,
) -> Path:
    requirements_dir = destination / "requirements"
    shutil.copytree(
        pristine_requirements,
        requirements_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    target = requirements_dir / relative_target
    staged = target.with_suffix(target.suffix + ".reqpilot-candidate")
    shutil.copyfile(candidate, staged)
    os.replace(staged, target)
    return requirements_dir


def prove_post_replace_rollback(
    pristine_requirements: Path,
    valid_candidate: Path,
    relative_target: str,
    destination: Path,
    command_prefix: tuple[str, ...],
    *,
    cwd: Path,
) -> bool:
    """Replace a temp-project source, inject a failure, and restore its backup."""

    requirements_dir = destination / "requirements"
    shutil.copytree(
        pristine_requirements,
        requirements_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    before = hash_manifest(requirements_dir)
    target = requirements_dir / relative_target
    backup = destination / "backups" / relative_target
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target, backup)

    staged = target.with_suffix(target.suffix + ".reqpilot-candidate")
    shutil.copyfile(valid_candidate, staged)
    try:
        os.replace(staged, target)
        if sha256_file(target) == before[relative_target]:
            raise SpikeFailure("Rollback injection did not install the candidate.")
        raise RuntimeError("injected failure after os.replace")
    except RuntimeError:
        restore = target.with_suffix(target.suffix + ".reqpilot-restore")
        shutil.copyfile(backup, restore)
        os.replace(restore, target)

    rollback_export = native_json_export(
        command_prefix,
        requirements_dir,
        destination / "exports" / "rollback",
        cwd=cwd,
    )
    require_success(rollback_export, phase="Post-replace rollback validation")
    after = hash_manifest(requirements_dir)
    if before != after:
        raise SpikeFailure("Backup restore did not reproduce the pre-write manifest.")
    return True


def normalized_relations(node: dict[str, Any]) -> list[dict[str, Any]]:
    relations = node.get("RELATIONS", [])
    if not isinstance(relations, list):
        raise SpikeFailure("Native JSON RELATIONS value is not a list.")
    return relations


def assert_semantic_round_trip(
    before: ProjectSnapshot,
    after: ProjectSnapshot,
) -> int:
    if before.documents != after.documents:
        raise SpikeFailure("Document metadata or resolved grammar changed during round-trip.")
    if before.document_order != after.document_order:
        raise SpikeFailure("Document or requirement order changed during round-trip.")
    if set(before.nodes) != set(after.nodes):
        raise SpikeFailure("Requirement UID set changed during round-trip.")

    preserved_fields = 0
    for uid in sorted(before.nodes):
        before_node = before.nodes[uid]
        after_node = after.nodes[uid]
        if before_node.get("MID") != after_node.get("MID"):
            raise SpikeFailure(f"MID changed for {uid}.")
        if normalized_relations(before_node) != normalized_relations(after_node):
            raise SpikeFailure(f"Relations changed for {uid}.")

        ignored = {"RELATIONS"}
        if uid == TARGET_UID:
            ignored.add("RATIONALE")
        before_fields = {key: value for key, value in before_node.items() if key not in ignored}
        after_fields = {key: value for key, value in after_node.items() if key not in ignored}
        if before_fields != after_fields:
            changed = sorted(
                key
                for key in set(before_fields) | set(after_fields)
                if before_fields.get(key) != after_fields.get(key)
            )
            raise SpikeFailure(f"Non-target fields changed for {uid}: {changed}.")
        preserved_fields += len(before_fields)

    target_rationale = after.nodes[TARGET_UID].get("RATIONALE")
    if target_rationale != MUTATED_RATIONALE:
        raise SpikeFailure(
            "Unicode multiline value was not exact after native JSON re-read: "
            f"{target_rationale!r}."
        )
    return preserved_fields


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    requirements_dir = repo_root / "requirements"
    if not requirements_dir.is_dir():
        raise SpikeFailure(f"Requirements directory does not exist: {requirements_dir}.")

    command_prefix = strictdoc_command_prefix()
    assert_exact_version(command_prefix, cwd=repo_root)
    canonical_before = hash_manifest(requirements_dir)
    if not canonical_before:
        raise SpikeFailure("No canonical requirement source files were found.")

    with tempfile.TemporaryDirectory(prefix="reqpilot-strictdoc-spike-") as temp_name:
        work_dir = Path(temp_name)
        pristine_requirements = work_dir / "pristine" / "requirements"
        shutil.copytree(
            requirements_dir,
            pristine_requirements,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        pristine_before = hash_manifest(pristine_requirements)
        if pristine_before != canonical_before:
            raise SpikeFailure("Temporary pristine copy does not match canonical sources.")

        baseline_export = native_json_export(
            command_prefix,
            pristine_requirements,
            work_dir / "exports" / "baseline",
            cwd=repo_root,
        )
        before_snapshot = snapshot(require_success(baseline_export, phase="Baseline export"))

        valid_candidate, invalid_candidate, relative_target = create_model_candidates(
            pristine_requirements,
            work_dir,
        )

        valid_requirements = disposable_project_with_candidate(
            pristine_requirements,
            valid_candidate,
            relative_target,
            work_dir / "valid-project",
        )
        valid_export = native_json_export(
            command_prefix,
            valid_requirements,
            work_dir / "exports" / "valid-round-trip",
            cwd=repo_root,
        )
        after_snapshot = snapshot(require_success(valid_export, phase="Round-trip export"))
        preserved_fields = assert_semantic_round_trip(before_snapshot, after_snapshot)

        post_replace_rollback_restored = prove_post_replace_rollback(
            pristine_requirements,
            valid_candidate,
            relative_target,
            work_dir / "rollback-project",
            command_prefix,
            cwd=repo_root,
        )

        invalid_requirements = disposable_project_with_candidate(
            pristine_requirements,
            invalid_candidate,
            relative_target,
            work_dir / "invalid-project",
        )
        invalid_export = native_json_export(
            command_prefix,
            invalid_requirements,
            work_dir / "exports" / "invalid-candidate",
            cwd=repo_root,
        )
        if invalid_export.returncode == 0:
            raise SpikeFailure("StrictDoc accepted the candidate that is missing required UID.")
        invalid_diagnostic = f"{invalid_export.stdout}\n{invalid_export.stderr}"
        expected_diagnostic = "missing a field that is required by grammar: UID"
        if expected_diagnostic not in invalid_diagnostic:
            raise SpikeFailure(
                "StrictDoc rejected the invalid candidate for an unexpected reason:\n"
                f"{invalid_diagnostic}"
            )

        pristine_after = hash_manifest(pristine_requirements)
        if pristine_before != pristine_after:
            raise SpikeFailure("Pristine temporary source changed after candidate rejection.")
        valid_candidate_digest = sha256_file(valid_candidate)

    canonical_after = hash_manifest(requirements_dir)
    if canonical_before != canonical_after:
        raise SpikeFailure("Canonical requirement sources changed while running the spike.")

    report = {
        "status": "PASS",
        "strictdoc_version": PINNED_STRICTDOC_VERSION,
        "read_path": "native StrictDoc JSON export",
        "write_path": "StrictDoc parser/model/SDWriter API",
        "target_uid": TARGET_UID,
        "requirements": len(before_snapshot.nodes),
        "documents": len(before_snapshot.documents),
        "relations": before_snapshot.relation_count,
        "preserved_non_target_fields": preserved_fields,
        "canonical_files": len(canonical_before),
        "canonical_manifest_sha256": manifest_digest(canonical_before),
        "valid_candidate_sha256": valid_candidate_digest,
        "invalid_candidate_exit_code": invalid_export.returncode,
        "invalid_candidate_diagnostic": expected_diagnostic,
        "canonical_sources_unchanged": True,
        "temporary_pristine_sources_unchanged_after_rejection": True,
        "post_replace_rollback_restored": post_replace_rollback_restored,
        "subprocess_shell": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SpikeFailure as error:
        print(f"STRICTDOC SPIKE: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
