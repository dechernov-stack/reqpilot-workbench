"""Atomic YAML repository for UUID-keyed cross-tool trace links."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from filelock import FileLock
from ruamel.yaml import YAML

from reqpilot.adapters.capella import CapellaAdapter, CapellaAdapterError
from reqpilot.analytics_models import (
    ArchitectureRef,
    CapellaElement,
    CapellaState,
    LinkDiagnostic,
    TraceLink,
    TraceLinkCreate,
    TraceLinkList,
    TraceLinkUpdate,
    TraceLinkView,
    TraceValidationResult,
)
from reqpilot.config import ProjectConfig
from reqpilot.errors import NotFoundError, RevisionConflictError, ValidationError
from reqpilot.models import Requirement

SCHEMA_VERSION: Final = 1
RequirementProvider = Callable[[], Sequence[Requirement]]


class TraceLinkRepository:
    """Persist trace links with locking, backups, validation, and ``os.replace``."""

    def __init__(
        self,
        config: ProjectConfig,
        requirement_provider: RequirementProvider,
        capella: CapellaAdapter,
    ) -> None:
        self.config = config
        self.path = config.resolve_repo_path(config.trace_links.path)
        self.requirement_provider = requirement_provider
        self.capella = capella
        state_dir = config.ensure_state_dir()
        self.lock = FileLock(str(state_dir / "trace-links.lock"), timeout=30)
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.indent(mapping=2, sequence=4, offset=2)

    @property
    def revision(self) -> str:
        """Return a revision hash for optimistic concurrency."""

        if not self.path.is_file():
            return hashlib.sha256(b"schema_version: 1\nlinks: []\n").hexdigest()
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def list_links(self) -> TraceLinkList:
        """Return links resolved by requirement UID/MID and architecture UUID."""

        with self.lock:
            links = self._read_links()
            revision = self.revision
        views = [self._resolve(link) for link in links]
        return TraceLinkList(items=views, total=len(views), revision=revision)

    def get(self, link_id: str) -> TraceLinkView:
        """Return one resolved link by stable link ID."""

        for link in self.list_links().items:
            if link.id == link_id:
                return link
        raise NotFoundError("Trace link", link_id)

    def create(self, payload: TraceLinkCreate) -> TraceLinkView:
        """Create one validated link with a stable sequential ID."""

        with self.lock:
            base_revision = self.revision
            self._check_revision(payload.revision, actual=base_revision)
            links = self._read_links()
            link_id = self._next_id(links)
            now = datetime.now(UTC)
            link = TraceLink(
                id=link_id,
                requirement=payload.requirement,
                architecture=payload.architecture,
                relation=payload.relation,
                rationale=payload.rationale,
                created_at=now,
                updated_at=now,
            )
            candidate = [*links, link]
            self._assert_changed_link_valid(candidate, link_id)
            self._write_links(candidate, base_revision=base_revision)
        return self._resolve(link)

    def update(self, link_id: str, payload: TraceLinkUpdate) -> TraceLinkView:
        """Update one link without changing its ID or creation timestamp."""

        with self.lock:
            base_revision = self.revision
            self._check_revision(payload.revision, actual=base_revision)
            links = self._read_links()
            current = next((link for link in links if link.id == link_id), None)
            if current is None:
                raise NotFoundError("Trace link", link_id)
            changes = payload.model_dump(exclude_none=True, exclude={"revision"})
            changes["updated_at"] = datetime.now(UTC)
            current_value = current.model_dump()
            current_value.update(changes)
            updated = TraceLink.model_validate(current_value)
            candidate = [updated if link.id == link_id else link for link in links]
            self._assert_changed_link_valid(candidate, link_id)
            self._write_links(candidate, base_revision=base_revision)
        return self._resolve(updated)

    def delete(self, link_id: str, *, revision: str) -> str:
        """Delete one addressed link and return the new repository revision."""

        with self.lock:
            base_revision = self.revision
            self._check_revision(revision, actual=base_revision)
            links = self._read_links()
            if not any(link.id == link_id for link in links):
                raise NotFoundError("Trace link", link_id)
            self._write_links(
                [link for link in links if link.id != link_id],
                base_revision=base_revision,
            )
            return self.revision

    def validate(self) -> TraceValidationResult:
        """Validate IDs, pairs, UID/MID resolution, and architecture UUIDs."""

        with self.lock:
            links = self._read_links()
            revision = self.revision
        diagnostics = self._diagnostics(links)
        return TraceValidationResult(
            valid=not any(item.severity == "error" for item in diagnostics),
            revision=revision,
            diagnostics=diagnostics,
        )

    def refresh_snapshots(self, *, revision: str | None = None) -> TraceLinkList:
        """Refresh names/types explicitly while preserving UUIDs and link IDs."""

        with self.lock:
            base_revision = self.revision
            self._check_revision(revision, actual=base_revision)
            links = self._read_links()
            index = self.capella.ensure_loaded()
            if index is None:
                raise ValidationError("Architecture index is unavailable.", [])
            by_uuid = {element.uuid: element for element in index.elements}
            now = datetime.now(UTC)
            refreshed: list[TraceLink] = []
            for link in links:
                element = by_uuid.get(link.architecture.uuid)
                if element is None or element.model_id != link.architecture.model_id:
                    refreshed.append(link)
                    continue
                architecture = ArchitectureRef(
                    model_id=link.architecture.model_id,
                    uuid=link.architecture.uuid,
                    type=element.type,
                    name_snapshot=element.name,
                )
                if architecture == link.architecture:
                    refreshed.append(link)
                else:
                    refreshed.append(
                        link.model_copy(update={"architecture": architecture, "updated_at": now})
                    )
            self._write_links(refreshed, base_revision=base_revision)
        return self.list_links()

    def _read_links(self) -> list[TraceLink]:
        if not self.path.is_file():
            return []
        try:
            raw: Any = self.yaml.load(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValidationError(f"Cannot read trace-links.yaml: {error}", []) from error
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            raise ValidationError("trace-links.yaml must use schema_version: 1.", [])
        values = raw.get("links")
        if not isinstance(values, list):
            raise ValidationError("trace-links.yaml links must be a list.", [])
        try:
            return [TraceLink.model_validate(value) for value in values]
        except ValueError as error:
            raise ValidationError(f"Invalid trace-link record: {error}", []) from error

    def _write_links(self, links: Sequence[TraceLink], *, base_revision: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "links": [link.model_dump(mode="json") for link in links],
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                self.yaml.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            # Parse the exact candidate before it can replace the canonical file.
            candidate: Any = self.yaml.load(temporary.read_text(encoding="utf-8"))
            if not isinstance(candidate, dict) or candidate.get("schema_version") != 1:
                raise ValidationError("Generated trace-link candidate is invalid.", [])
            for value in candidate.get("links", []):
                TraceLink.model_validate(value)
            if self.path.exists():
                shutil.copy2(self.path, self.path.with_suffix(f"{self.path.suffix}.bak"))
            self._check_revision(base_revision)
            os.replace(temporary, self.path)
            self._fsync_directory(self.path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _check_revision(self, expected: str | None, *, actual: str | None = None) -> None:
        if expected is None:
            return
        current = self.revision if actual is None else actual
        if expected != current:
            raise RevisionConflictError(expected, current)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _next_id(links: Sequence[TraceLink]) -> str:
        numbers = [int(link.id.removeprefix("TL-")) for link in links]
        return f"TL-{max(numbers, default=0) + 1:04d}"

    def _requirement_map(self) -> dict[str, Requirement]:
        return {requirement.uid: requirement for requirement in self.requirement_provider()}

    def _architecture_map(self) -> dict[str, CapellaElement] | None:
        index = self.capella.ensure_loaded()
        if index is None:
            status = self.capella.status()
            if status.state == CapellaState.ERROR:
                raise CapellaAdapterError(status.message)
            return None
        return {element.uuid: element for element in index.elements}

    def _resolve(self, link: TraceLink) -> TraceLinkView:
        requirements = self._requirement_map()
        requirement = requirements.get(link.requirement.uid)
        if requirement is None or requirement.mid != link.requirement.mid:
            return TraceLinkView(
                **link.model_dump(),
                status="broken_requirement",
                current_name=None,
                snapshot_stale=False,
            )
        try:
            architecture = self._architecture_map()
        except CapellaAdapterError:
            architecture = None
        if architecture is None:
            return TraceLinkView(
                **link.model_dump(),
                status="architecture_unavailable",
                current_name=None,
                snapshot_stale=False,
            )
        element = architecture.get(link.architecture.uuid)
        if element is None or element.model_id != link.architecture.model_id:
            return TraceLinkView(
                **link.model_dump(),
                status="broken_architecture",
                current_name=None,
                snapshot_stale=False,
            )
        return TraceLinkView(
            **link.model_dump(),
            status="valid",
            current_name=element.name,
            snapshot_stale=(
                element.name != link.architecture.name_snapshot
                or element.type != link.architecture.type
            ),
        )

    def _diagnostics(self, links: Sequence[TraceLink]) -> list[LinkDiagnostic]:
        diagnostics: list[LinkDiagnostic] = []
        requirements = self._requirement_map()
        architecture: dict[str, CapellaElement] | None
        try:
            architecture = self._architecture_map()
        except Exception as error:
            architecture = None
            diagnostics.append(
                LinkDiagnostic(
                    severity="error",
                    code="architecture_load_failed",
                    message=str(error),
                )
            )
        seen_ids: set[str] = set()
        seen_pairs: set[tuple[str, str, str, str]] = set()
        for link in links:
            if link.id in seen_ids:
                diagnostics.append(
                    LinkDiagnostic(
                        severity="error",
                        code="duplicate_id",
                        message=f"Duplicate trace-link ID {link.id}.",
                        link_id=link.id,
                    )
                )
            seen_ids.add(link.id)
            pair = (
                link.requirement.mid,
                link.architecture.model_id,
                link.architecture.uuid,
                link.relation,
            )
            if pair in seen_pairs:
                diagnostics.append(
                    LinkDiagnostic(
                        severity="error",
                        code="duplicate_pair",
                        message="Duplicate MID + model_id + UUID + relation pair.",
                        link_id=link.id,
                    )
                )
            seen_pairs.add(pair)
            requirement = requirements.get(link.requirement.uid)
            if requirement is None:
                diagnostics.append(
                    LinkDiagnostic(
                        severity="error",
                        code="unknown_requirement_uid",
                        message=f"Requirement UID {link.requirement.uid} does not resolve.",
                        link_id=link.id,
                    )
                )
            elif requirement.mid != link.requirement.mid:
                diagnostics.append(
                    LinkDiagnostic(
                        severity="error",
                        code="requirement_mid_mismatch",
                        message=(
                            f"UID {link.requirement.uid} resolves to MID {requirement.mid}, "
                            f"not {link.requirement.mid}."
                        ),
                        link_id=link.id,
                    )
                )
            if architecture is None:
                if self.capella.status().state in {
                    CapellaState.DISABLED,
                    CapellaState.NOT_CONFIGURED,
                }:
                    diagnostics.append(
                        LinkDiagnostic(
                            severity="warning",
                            code="architecture_unavailable",
                            message=(
                                "Architecture UUID was not checked because Capella is unavailable."
                            ),
                            link_id=link.id,
                        )
                    )
                continue
            element = architecture.get(link.architecture.uuid)
            if element is None or element.model_id != link.architecture.model_id:
                diagnostics.append(
                    LinkDiagnostic(
                        severity="error",
                        code="broken_architecture_uuid",
                        message=(
                            f"Architecture UUID {link.architecture.uuid} does not resolve "
                            f"in model {link.architecture.model_id}."
                        ),
                        link_id=link.id,
                    )
                )
            elif (
                element.name != link.architecture.name_snapshot
                or element.type != link.architecture.type
            ):
                diagnostics.append(
                    LinkDiagnostic(
                        severity="warning",
                        code="stale_snapshot",
                        message=(
                            "UUID still resolves, but snapshot "
                            f"{link.architecture.name_snapshot!r} "
                            f"differs from current name {element.name!r}."
                        ),
                        link_id=link.id,
                    )
                )
        if not diagnostics:
            diagnostics.append(
                LinkDiagnostic(
                    severity="info",
                    code="trace_links_valid",
                    message=f"Validated {len(links)} trace links.",
                )
            )
        return diagnostics

    def _assert_changed_link_valid(self, links: Sequence[TraceLink], link_id: str) -> None:
        diagnostics = self._diagnostics(links)
        errors = [
            item
            for item in diagnostics
            if item.severity == "error"
            and (item.link_id == link_id or item.code in {"duplicate_id", "duplicate_pair"})
        ]
        if errors:
            raise ValidationError(
                f"Trace link {link_id} is invalid.",
                [item.model_dump(mode="json") for item in errors],
            )
