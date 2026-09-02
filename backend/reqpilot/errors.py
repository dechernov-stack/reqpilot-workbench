"""Typed service errors translated to stable HTTP responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=False)
class ReqPilotError(Exception):
    """Base error with an API-safe code and diagnostic payload."""

    code: str
    message: str
    status_code: int = 400
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return self.message

    def as_detail(self) -> dict[str, Any]:
        """Return a JSON-serializable FastAPI error detail."""

        detail: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.diagnostics:
            detail["diagnostics"] = self.diagnostics
        return detail


class ConfigurationError(ReqPilotError):
    """Raised when project.yaml violates a safety invariant."""

    def __init__(self, message: str) -> None:
        super().__init__("configuration_error", message, 500)


class StrictDocCommandError(ReqPilotError):
    """Raised when a native StrictDoc command fails."""

    def __init__(self, message: str, diagnostics: list[dict[str, Any]]) -> None:
        super().__init__("strictdoc_command_failed", message, 422, diagnostics)


class RevisionConflictError(ReqPilotError):
    """Raised when optimistic concurrency detects a stale client."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            "revision_conflict",
            f"Revision conflict: expected {expected!r}, current revision is {actual!r}.",
            409,
        )


class NotFoundError(ReqPilotError):
    """Raised when an addressed domain object does not exist."""

    def __init__(self, kind: str, identifier: str) -> None:
        super().__init__("not_found", f"{kind} {identifier!r} was not found.", 404)


class ValidationError(ReqPilotError):
    """Raised when a candidate would make the canonical project invalid."""

    def __init__(self, message: str, diagnostics: list[dict[str, Any]]) -> None:
        super().__init__("validation_failed", message, 422, diagnostics)


class PathSecurityError(ReqPilotError):
    """Raised when a path escapes its configured allowlist/root."""

    def __init__(self, message: str) -> None:
        super().__init__("path_rejected", message, 400)
