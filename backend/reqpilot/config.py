"""Load and validate the single ReqPilot project configuration."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from reqpilot.errors import ConfigurationError, PathSecurityError

UID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


class ProjectIdentity(BaseModel):
    """Human and stable project identity."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)


class ServerSettings(BaseModel):
    """Loopback-only server configuration."""

    model_config = ConfigDict(extra="forbid")
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=8080, ge=1024, le=65535)


class StrictDocSettings(BaseModel):
    """StrictDoc canonical paths and managed-document allowlist."""

    model_config = ConfigDict(extra="forbid")
    root: str
    config: str
    managed_documents: list[str] = Field(min_length=1)
    document_mids: dict[str, str] = Field(min_length=1)
    export_root: str
    deleted_uids: str = "deleted-uids.json"

    @field_validator("managed_documents")
    @classmethod
    def unique_documents(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("strictdoc.managed_documents contains duplicates")
        return value


class CapellaSettings(BaseModel):
    """Read-only Capella settings; the adapter is implemented in Stage 3."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["disabled", "live", "fixture"] = "disabled"
    model_path: str | None = None
    entrypoint: str | None = None
    read_only: Literal[True] = True
    cache_path: str


class TraceLinkSettings(BaseModel):
    """Trace-link repository location."""

    model_config = ConfigDict(extra="forbid")
    path: str


class FixtureSettings(BaseModel):
    """Explicit fixture boundary configuration."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    path: str


class ProjectConfig(BaseModel):
    """Validated content of project.yaml plus its repository root."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    schema_version: Literal[1]
    project: ProjectIdentity
    server: ServerSettings
    strictdoc: StrictDocSettings
    capella: CapellaSettings
    trace_links: TraceLinkSettings
    fixture: FixtureSettings
    repo_root: Path = Field(exclude=True)

    @model_validator(mode="after")
    def validate_paths(self) -> ProjectConfig:
        root = self.repo_root.resolve()
        for configured in (
            self.strictdoc.root,
            self.strictdoc.config,
            self.strictdoc.export_root,
            self.strictdoc.deleted_uids,
            self.trace_links.path,
            self.capella.cache_path,
            self.fixture.path,
        ):
            self.reject_repo_path_symlinks(configured)
        strictdoc_root = self.resolve_repo_path(self.strictdoc.root)
        config_path = self.resolve_repo_path(self.strictdoc.config)
        export_root = self.resolve_repo_path(self.strictdoc.export_root)
        deleted_uids = self.resolve_repo_path(self.strictdoc.deleted_uids)
        trace_links = self.resolve_repo_path(self.trace_links.path)
        capella_cache = self.resolve_repo_path(self.capella.cache_path)
        fixture_path = self.resolve_repo_path(self.fixture.path)
        if not strictdoc_root.is_dir():
            raise ValueError(f"StrictDoc root does not exist: {strictdoc_root}")
        if not config_path.is_file():
            raise ValueError(f"StrictDoc config does not exist: {config_path}")
        try:
            config_path.relative_to(strictdoc_root)
        except ValueError as error:
            raise ValueError("StrictDoc config must be inside the requirements root") from error
        for configured in self.strictdoc.managed_documents:
            self.reject_repo_path_symlinks(configured)
            path = self.resolve_repo_path(configured)
            if not path.is_file() or path.suffix.lower() != ".sdoc":
                raise ValueError(f"Managed StrictDoc document is invalid: {configured}")
            try:
                path.relative_to(strictdoc_root)
            except ValueError as error:
                raise ValueError(
                    f"Managed document escapes StrictDoc root: {configured}"
                ) from error
        configured_documents = {
            self.resolve_repo_path(value) for value in self.strictdoc.managed_documents
        }
        mapped_documents = {
            self.resolve_repo_path(value) for value in self.strictdoc.document_mids.values()
        }
        if len(self.strictdoc.document_mids) != len(configured_documents):
            raise ValueError("strictdoc.document_mids must contain one unique MID per document")
        if mapped_documents != configured_documents:
            raise ValueError(
                "strictdoc.document_mids must map exactly the managed document allowlist"
            )
        if export_root == root:
            raise ValueError("StrictDoc export root cannot be the repository root")
        try:
            export_root.relative_to(strictdoc_root)
        except ValueError:
            pass
        else:
            raise ValueError(
                "StrictDoc export root cannot be equal to or inside the requirements root"
            )
        if (
            deleted_uids == root
            or deleted_uids.suffix.lower() != ".json"
            or not deleted_uids.is_file()
        ):
            raise ValueError("StrictDoc deleted UID registry must be a JSON file")
        try:
            deleted_uids.relative_to(strictdoc_root)
        except ValueError:
            pass
        else:
            raise ValueError("StrictDoc deleted UID registry cannot overlap requirements sources")
        state_root = root / ".reqpilot"
        try:
            deleted_uids.relative_to(state_root)
        except ValueError:
            pass
        else:
            raise ValueError("StrictDoc deleted UID registry must be tracked outside .reqpilot")
        try:
            tombstone_payload = json.loads(deleted_uids.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("StrictDoc deleted UID registry is not valid JSON") from error
        if not isinstance(tombstone_payload, dict) or set(tombstone_payload) != {"uids"}:
            raise ValueError("StrictDoc deleted UID registry has an invalid shape")
        tombstone_values = tombstone_payload["uids"]
        if (
            not isinstance(tombstone_values, list)
            or any(
                not isinstance(item, str) or not UID_PATTERN.fullmatch(item)
                for item in tombstone_values
            )
            or len(tombstone_values) != len(set(tombstone_values))
        ):
            raise ValueError("StrictDoc deleted UID registry has invalid UIDs")
        if trace_links.suffix.lower() not in {".yaml", ".yml"} or not trace_links.is_file():
            raise ValueError("Trace-link repository must be an existing YAML file")
        try:
            trace_links.relative_to(strictdoc_root)
        except ValueError:
            pass
        else:
            raise ValueError("Trace-link repository cannot overlap requirements sources")
        if trace_links in {config_path, deleted_uids}:
            raise ValueError("Trace-link repository overlaps another canonical file")
        if capella_cache == root or capella_cache.suffix.lower() != ".json":
            raise ValueError("Capella cache path must address a JSON file")
        if capella_cache.exists() and not capella_cache.is_file():
            raise ValueError("Capella cache path must not address a directory")
        try:
            capella_cache.relative_to(strictdoc_root)
        except ValueError:
            pass
        else:
            raise ValueError("Capella cache cannot overlap requirements sources")
        if capella_cache in {config_path, deleted_uids, trace_links}:
            raise ValueError("Capella cache overlaps a canonical file")
        if self.fixture.enabled and self.capella.mode != "fixture":
            raise ValueError("fixture.enabled requires capella.mode=fixture")
        if self.fixture.enabled and not fixture_path.is_file():
            raise ValueError("Enabled architecture fixture must be an existing file")
        return self

    def resolve_repo_path(self, configured: str) -> Path:
        """Resolve a configured relative path and reject repository escapes."""

        path = (self.repo_root / configured).resolve()
        try:
            path.relative_to(self.repo_root.resolve())
        except ValueError as error:
            raise PathSecurityError(
                f"Configured path escapes repository root: {configured!r}."
            ) from error
        return path

    def reject_repo_path_symlinks(self, configured: str) -> None:
        """Reject every existing symlink component in a configured repo path."""

        root = self.repo_root.resolve(strict=True)
        lexical = Path(os.path.abspath(root / configured))
        try:
            relative = lexical.relative_to(root)
        except ValueError as error:
            raise PathSecurityError(
                f"Configured path escapes repository root: {configured!r}."
            ) from error
        cursor = root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise PathSecurityError(
                    f"Configured path must not contain symlinks: {configured!r}."
                )

    def ensure_state_dir(self, *relative_parts: str) -> Path:
        """Create a non-symlinked state directory confined to the repository.

        Validation is deliberately performed both before and after ``mkdir`` so
        that an existing (including broken) ``.reqpilot`` symlink is never used
        as a write target.  Nested state directories receive the same checks.
        """

        root = self.repo_root.resolve(strict=True)
        relative = Path(*relative_parts) if relative_parts else Path()
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise PathSecurityError("ReqPilot state directory must use safe relative parts.")

        state_root = root / ".reqpilot"
        target = state_root / relative
        self._validate_state_dir_path(state_root, root, strict=False)
        self._validate_state_dir_path(target, root, strict=False)
        try:
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            raise PathSecurityError(
                f"Cannot create ReqPilot state directory safely: {target}."
            ) from error
        self._validate_state_dir_path(state_root, root, strict=True)
        return self._validate_state_dir_path(target, root, strict=True)

    @staticmethod
    def _validate_state_dir_path(path: Path, root: Path, *, strict: bool) -> Path:
        """Reject symlink components and paths resolving outside ``root``."""

        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise PathSecurityError(
                f"ReqPilot state directory escapes repository root: {path}."
            ) from error
        cursor = root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise PathSecurityError(
                    f"ReqPilot state directory must not contain symlinks: {cursor}."
                )
        try:
            resolved = path.resolve(strict=strict)
            resolved.relative_to(root)
        except (OSError, ValueError) as error:
            raise PathSecurityError(
                f"ReqPilot state directory resolves outside repository root: {path}."
            ) from error
        if strict and not resolved.is_dir():
            raise PathSecurityError(f"ReqPilot state path is not a directory: {path}.")
        return resolved

    @property
    def requirements_dir(self) -> Path:
        """Return the canonical StrictDoc source directory."""

        return self.resolve_repo_path(self.strictdoc.root)

    @property
    def strictdoc_config_path(self) -> Path:
        """Return the native StrictDoc Python configuration path."""

        return self.resolve_repo_path(self.strictdoc.config)

    @property
    def export_root(self) -> Path:
        """Return the generated StrictDoc export root."""

        return self.resolve_repo_path(self.strictdoc.export_root)

    @property
    def deleted_uid_registry_path(self) -> Path:
        """Return the tracked canonical registry of deleted requirement UIDs."""

        return self.resolve_repo_path(self.strictdoc.deleted_uids)

    @property
    def managed_document_paths(self) -> tuple[Path, ...]:
        """Return the canonical managed-document allowlist."""

        return tuple(self.resolve_repo_path(value) for value in self.strictdoc.managed_documents)

    @property
    def managed_documents_by_mid(self) -> dict[str, Path]:
        """Return the explicit stable document MID to managed path mapping."""

        return {
            mid: self.resolve_repo_path(configured)
            for mid, configured in self.strictdoc.document_mids.items()
        }

    def managed_document(self, value: str) -> Path:
        """Resolve an API document value to an exact managed document."""

        candidates = {path.name: path for path in self.managed_document_paths} | {
            path.relative_to(self.repo_root).as_posix(): path
            for path in self.managed_document_paths
        }
        path = candidates.get(value)
        if path is None:
            raise PathSecurityError(f"Document is not managed by ReqPilot: {value!r}.")
        return path


def load_project_config(path: Path) -> ProjectConfig:
    """Load project.yaml safely and return a validated configuration."""

    lexical_path = Path(os.path.abspath(path))
    if lexical_path.is_symlink():
        raise ConfigurationError("Project configuration must not be a symlink")
    config_path = lexical_path.resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"Project configuration does not exist: {config_path}")
    yaml = YAML(typ="safe")
    try:
        loaded: Any = yaml.load(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("project.yaml root must be a mapping")
        loaded["repo_root"] = config_path.parent
        return ProjectConfig.model_validate(loaded)
    except (OSError, ValueError, YAMLError) as error:
        raise ConfigurationError(f"Invalid project configuration: {error}") from error
