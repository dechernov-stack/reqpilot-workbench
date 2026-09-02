"""Transactional StrictDoc model writer for managed `.sdoc` documents."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import time
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Final

from strictdoc.backend.sdoc.models.node import SDocNode  # type: ignore[import-untyped]
from strictdoc.backend.sdoc.models.object_factory import (  # type: ignore[import-untyped]
    SDocObjectFactory,
)
from strictdoc.backend.sdoc.models.reference import (  # type: ignore[import-untyped]
    ParentReqReference,
)
from strictdoc.backend.sdoc.writer import SDWriter  # type: ignore[import-untyped]
from strictdoc.core.document_iterator import (  # type: ignore[import-untyped]
    SDocDocumentIterator,
)
from strictdoc.core.project_config import ProjectConfigLoader  # type: ignore[import-untyped]
from strictdoc.core.traceability_index_builder import (  # type: ignore[import-untyped]
    TraceabilityIndexBuilder,
)
from strictdoc.helpers.mid import MID  # type: ignore[import-untyped]
from strictdoc.helpers.parallelizer import Parallelizer  # type: ignore[import-untyped]

from reqpilot.errors import (
    NotFoundError,
    ReqPilotError,
    RevisionConflictError,
    ValidationError,
)
from reqpilot.models import Relation, Requirement, RequirementCreate, RequirementUpdate
from reqpilot.strictdoc_adapter import StrictDocAdapter

FIELD_MAP: Final = {
    "type": "TYPE",
    "status": "STATUS",
    "priority": "PRIORITY",
    "verification_method": "VERIFICATION_METHOD",
    "owner": "OWNER",
    "source": "SOURCE",
    "tags": "TAGS",
    "title": "TITLE",
    "statement": "STATEMENT",
    "rationale": "RATIONALE",
    "acceptance_criteria": "ACCEPTANCE_CRITERIA",
    "comment": "COMMENT",
}
BACKUPS_PER_DOCUMENT: Final = 10
UID_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


class SafeStrictDocWriter:
    """Mutate StrictDoc objects and commit only fully validated candidates."""

    def __init__(self, adapter: StrictDocAdapter) -> None:
        self.adapter = adapter
        self.config = adapter.config
        self.state_dir = self.config.ensure_state_dir()
        self.staging_root = self.config.ensure_state_dir("staging")
        self.backup_root = self.config.ensure_state_dir("backups")
        self.model_output_dir = self.config.ensure_state_dir("model-api-output")
        self.tombstone_path = self.config.deleted_uid_registry_path

    def create(self, payload: RequirementCreate) -> Requirement:
        """Append a requirement to an allowlisted document transactionally."""

        target_path = self.config.managed_document(payload.document)
        with self.adapter.lock:
            base_revision = self.adapter.calculate_revision()
            if payload.revision is not None:
                self._assert_revision(payload.revision, base_revision)
            existing = self.adapter.refresh_locked()
            if any(item.uid == payload.uid for item in existing.items):
                raise ValidationError(f"Requirement UID {payload.uid!r} already exists.", [])
            if payload.uid in self._read_tombstones():
                raise ValidationError(
                    f"Deleted UID {payload.uid!r} cannot be reused.",
                    [],
                )
            project_config, traceability_index = self._load_model()
            document = self._document_for_path(traceability_index, target_path)
            node = SDocObjectFactory.create_requirement(
                parent=document,
                node_type="REQUIREMENT",
                uid=payload.uid,
            )
            node.reserved_mid = MID.create()
            node.mid_permanent = True
            self._apply_fields(
                node,
                payload.model_dump(
                    exclude={"document", "uid", "revision", "relations"},
                ),
            )
            node.relations = self._build_relations(node, payload.relations or [])
            document.section_contents.append(node)
            content = SDWriter(project_config).write(document)
            self._commit_document(target_path, content, base_revision=base_revision)
            return self.adapter.get_requirement(payload.uid)

    def update(self, uid: str, payload: RequirementUpdate) -> Requirement:
        """Partially update editable fields while preserving UID, MID, and unknown fields."""

        with self.adapter.lock:
            base_revision = self.adapter.calculate_revision()
            if payload.revision is None:
                raise ReqPilotError(
                    "revision_required",
                    "Requirement update needs revision or If-Match.",
                    428,
                )
            self._assert_revision(payload.revision, base_revision)
            project_config, traceability_index = self._load_model()
            document, node, target_path = self._find_node(traceability_index, uid)
            stable_uid = node.reserved_uid
            stable_mid = str(node.reserved_mid)
            changes = payload.model_dump(exclude_unset=True, exclude={"revision", "relations"})
            self._apply_fields(node, changes)
            if "relations" in payload.model_fields_set:
                node.relations = self._build_relations(node, payload.relations or [])
            if node.reserved_uid != stable_uid or str(node.reserved_mid) != stable_mid:
                raise ValidationError("StrictDoc writer changed a stable UID or MID.", [])
            content = SDWriter(project_config).write(document)
            self._commit_document(target_path, content, base_revision=base_revision)
            updated = self.adapter.get_requirement(uid)
            if updated.mid != stable_mid:
                raise ValidationError("MID changed after StrictDoc native round-trip.", [])
            return updated

    def delete(self, uid: str, *, revision: str) -> str:
        """Delete an unreferenced requirement and permanently tombstone its UID."""

        with self.adapter.lock:
            base_revision = self.adapter.calculate_revision()
            self._assert_revision(revision, base_revision)
            registry_snapshot = self._snapshot_tombstones()
            project_config, traceability_index = self._load_model()
            document, node, target_path = self._find_node(traceability_index, uid)
            parent = node.parent
            if node not in parent.section_contents:
                raise ValidationError(f"Requirement {uid!r} cannot be removed from its parent.", [])
            previous_tombstones = self._read_tombstones(registry_snapshot[1])
            parent.section_contents.remove(node)
            content = SDWriter(project_config).write(document)
            self._commit_document(
                target_path,
                content,
                base_revision=base_revision,
                tombstone_values=previous_tombstones | {uid},
                tombstone_snapshot=registry_snapshot,
            )
            return self.adapter.revision

    def _assert_revision(self, expected: str, actual: str) -> None:
        normalized = expected.strip().removeprefix("W/").strip('"')
        if normalized != actual:
            raise RevisionConflictError(normalized, actual)

    def _load_model(self) -> tuple[Any, Any]:
        self.adapter.assert_safe_requirements_tree(self.config.requirements_dir)
        project_config = ProjectConfigLoader.load(
            str(self.config.requirements_dir),
            output_dir=str(self.model_output_dir),
        )
        parser_log = io.StringIO()
        try:
            with redirect_stdout(parser_log):
                index = TraceabilityIndexBuilder.create(
                    project_config=project_config,
                    parallelizer=Parallelizer.create(False),
                    skip_source_files=True,
                )
        except Exception as error:
            raise ValidationError(
                "StrictDoc model API could not parse the canonical project.",
                [
                    {
                        "severity": "error",
                        "source": "strictdoc-model",
                        "code": "parse_failed",
                        "message": str(error),
                        "details": {"stdout": parser_log.getvalue()[-20_000:]},
                    }
                ],
            ) from error
        return project_config, index

    def _document_for_path(self, index: Any, target_path: Path) -> Any:
        resolved_target = target_path.resolve()
        for document in index.document_tree.document_list:
            if document.meta is None:
                continue
            if Path(document.meta.input_doc_full_path).resolve() == resolved_target:
                return document
        raise NotFoundError("Managed document", target_path.name)

    def _find_node(self, index: Any, uid: str) -> tuple[Any, SDocNode, Path]:
        matches: list[tuple[Any, SDocNode, Path]] = []
        managed = {path.resolve() for path in self.config.managed_document_paths}
        for document in index.document_tree.document_list:
            if document.meta is None:
                continue
            source_path = Path(document.meta.input_doc_full_path).resolve()
            for node, _ in SDocDocumentIterator(document).all_content():
                if isinstance(node, SDocNode) and node.reserved_uid == uid:
                    if source_path not in managed:
                        raise ValidationError(
                            f"Requirement {uid!r} belongs to an unmanaged document.",
                            [],
                        )
                    matches.append((document, node, source_path))
        if not matches:
            raise NotFoundError("Requirement", uid)
        if len(matches) != 1:
            raise ValidationError(f"Requirement UID {uid!r} is not unique.", [])
        return matches[0]

    def _apply_fields(self, node: SDocNode, values: dict[str, Any]) -> None:
        for api_name, value in values.items():
            field_name = FIELD_MAP.get(api_name)
            if field_name is None:
                continue
            if api_name == "tags" and value is not None:
                value = ", ".join(value)
            if api_name == "comment" and (value is None or value == ""):
                node.ordered_fields_lookup.pop(field_name, None)
                continue
            node.set_field_value(field_name=field_name, form_field_index=0, value=value)

    @staticmethod
    def _build_relations(node: SDocNode, relations: list[Relation]) -> list[ParentReqReference]:
        return [ParentReqReference(node, relation.value, relation.role) for relation in relations]

    def _commit_document(
        self,
        target_path: Path,
        content: str,
        *,
        base_revision: str,
        tombstone_values: set[str] | None = None,
        tombstone_snapshot: tuple[bool, bytes] | None = None,
    ) -> None:
        target_path = target_path.resolve()
        if target_path not in {path.resolve() for path in self.config.managed_document_paths}:
            raise ValidationError("Writer target is outside the managed-document allowlist.", [])
        self._assert_revision(base_revision, self.adapter.calculate_revision())
        transaction_id = uuid.uuid4().hex
        stage_dir = self.staging_root / transaction_id
        staged_requirements = stage_dir / "requirements"
        source_temporary = target_path.with_name(
            f".{target_path.name}.reqpilot-{transaction_id}.tmp"
        )
        tombstone_temporary: Path | None = None
        try:
            shutil.copytree(
                self.config.requirements_dir,
                staged_requirements,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            relative_target = target_path.relative_to(self.config.requirements_dir.resolve())
            staged_target = staged_requirements / relative_target
            staged_target.write_text(content, encoding="utf-8")
            validation_output = stage_dir / "validation-output"
            command = self.adapter.run_native_export(
                staged_requirements,
                validation_output,
                export_format="json",
            )
            if command.returncode != 0:
                diagnostics = [
                    item.model_dump(mode="json")
                    for item in self.adapter.command_diagnostics(command)
                ]
                raise ValidationError(
                    "StrictDoc rejected the candidate; canonical sources are unchanged.",
                    diagnostics,
                )

            backup = self._create_backup(target_path, base_revision=base_revision)
            self._write_fsynced(source_temporary, content)
            if tombstone_values is not None:
                if tombstone_snapshot is None:
                    raise ReqPilotError(
                        "write_failed",
                        "A deleted-UID registry snapshot is required for deletion.",
                        500,
                    )
                tombstone_temporary = self.tombstone_path.with_name(
                    f".{self.tombstone_path.name}.reqpilot-{transaction_id}.tmp"
                )
                self._write_bytes_fsynced(
                    tombstone_temporary,
                    self._serialize_tombstones(tombstone_values),
                )

            # An editor or other process may ignore ReqPilot's advisory lock.
            # Check after native validation and immediately before replacement.
            self._assert_revision(base_revision, self.adapter.calculate_revision())
            source_replaced = False
            tombstones_replaced = False
            try:
                os.replace(source_temporary, target_path)
                source_replaced = True
                self._fsync_directory(target_path.parent)
                if tombstone_temporary is not None:
                    os.replace(tombstone_temporary, self.tombstone_path)
                    tombstones_replaced = True
                    self._fsync_directory(self.tombstone_path.parent)
                self.adapter.refresh_locked()
            except Exception as error:
                if source_replaced:
                    self._restore_backup(target_path, backup, transaction_id)
                if tombstone_snapshot is not None and (source_replaced or tombstones_replaced):
                    self._restore_tombstones(tombstone_snapshot, transaction_id)
                try:
                    self.adapter.refresh_locked()
                except Exception as rollback_error:
                    raise ReqPilotError(
                        "rollback_failed",
                        "Canonical write failed and rollback validation also failed: "
                        f"{rollback_error}",
                        500,
                    ) from error
                if isinstance(error, ReqPilotError):
                    raise
                raise ReqPilotError(
                    "write_failed",
                    "Atomic StrictDoc write failed; canonical transaction was "
                    f"rolled back: {error}",
                    500,
                ) from error
        finally:
            source_temporary.unlink(missing_ok=True)
            if tombstone_temporary is not None:
                tombstone_temporary.unlink(missing_ok=True)
            shutil.rmtree(stage_dir, ignore_errors=True)

    def _create_backup(self, target_path: Path, *, base_revision: str) -> Path:
        relative = target_path.relative_to(self.config.requirements_dir.resolve())
        destination_dir = self.backup_root / relative.parent
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        suffix = f"{time.time_ns()}-{base_revision[:12]}"
        backup = destination_dir / f"{relative.name}.{stamp}-{suffix}.bak"
        shutil.copy2(target_path, backup)
        self._rotate_backups(destination_dir, relative.name)
        return backup

    @staticmethod
    def _write_fsynced(path: Path, content: str) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())

    @staticmethod
    def _write_bytes_fsynced(path: Path, content: bytes) -> None:
        with path.open("wb") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _restore_backup(self, target_path: Path, backup: Path, transaction_id: str) -> None:
        rollback = target_path.with_name(f".{target_path.name}.rollback-{transaction_id}.tmp")
        shutil.copyfile(backup, rollback)
        with rollback.open("rb") as source:
            os.fsync(source.fileno())
        os.replace(rollback, target_path)
        self._fsync_directory(target_path.parent)

    @staticmethod
    def _rotate_backups(directory: Path, document_name: str) -> None:
        backups = sorted(
            directory.glob(f"{document_name}.*.bak"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for obsolete in backups[BACKUPS_PER_DOCUMENT:]:
            obsolete.unlink(missing_ok=True)

    def _snapshot_tombstones(self) -> tuple[bool, bytes]:
        if not self.tombstone_path.exists():
            raise ValidationError(
                "Deleted-UID safety metadata is missing; UID reuse cannot be checked.",
                [],
            )
        if self.tombstone_path.is_symlink() or not self.tombstone_path.is_file():
            raise ValidationError("Deleted-UID safety metadata is not a regular file.", [])
        try:
            return True, self.tombstone_path.read_bytes()
        except OSError as error:
            raise ValidationError("Deleted-UID safety metadata cannot be read.", []) from error

    def _read_tombstones(self, content: bytes | None = None) -> set[str]:
        if content is None:
            _exists, content = self._snapshot_tombstones()
        if not content:
            return set()
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("Deleted-UID safety metadata is invalid.", []) from error
        if not isinstance(payload, dict) or set(payload) != {"uids"}:
            raise ValidationError("Deleted-UID safety metadata has an invalid shape.", [])
        values = payload["uids"]
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not UID_PATTERN.fullmatch(item) for item in values)
            or len(values) != len(set(values))
        ):
            raise ValidationError("Deleted-UID safety metadata has invalid UIDs.", [])
        return set(values)

    @staticmethod
    def _serialize_tombstones(values: set[str]) -> bytes:
        return (json.dumps({"uids": sorted(values)}, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )

    def _restore_tombstones(self, snapshot: tuple[bool, bytes], transaction_id: str) -> None:
        existed, content = snapshot
        if not existed:
            if self.tombstone_path.exists() or self.tombstone_path.is_symlink():
                self.tombstone_path.unlink()
                self._fsync_directory(self.tombstone_path.parent)
            return
        rollback = self.tombstone_path.with_name(
            f".{self.tombstone_path.name}.rollback-{transaction_id}.tmp"
        )
        self._write_bytes_fsynced(rollback, content)
        os.replace(rollback, self.tombstone_path)
        self._fsync_directory(self.tombstone_path.parent)
