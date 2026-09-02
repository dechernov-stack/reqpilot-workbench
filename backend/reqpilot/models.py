"""Pydantic API and domain models for ReqPilot."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RequirementType = Literal["Stakeholder", "System", "Interface", "Software", "Safety", "TestCase"]
RequirementStatus = Literal["Draft", "Review", "Approved", "Deprecated"]
RequirementPriority = Literal["Low", "Medium", "High", "Critical"]
VerificationMethod = Literal["Inspection", "Analysis", "Demonstration", "Test", "NotApplicable"]
RelationRole = Literal["Refines", "Derives", "Verifies", "DependsOn"]


class DiagnosticSeverity(StrEnum):
    """Stable diagnostic levels exposed by the API."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Diagnostic(BaseModel):
    """Structured command, parser, or validation diagnostic."""

    severity: DiagnosticSeverity
    source: str
    code: str
    message: str
    document: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    """Normalized native StrictDoc relation."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["Parent"] = "Parent"
    value: str = Field(min_length=1)
    role: RelationRole


class RequirementBase(BaseModel):
    """Editable StrictDoc grammar fields."""

    model_config = ConfigDict(extra="forbid")
    type: RequirementType | None = None
    status: RequirementStatus | None = None
    priority: RequirementPriority | None = None
    verification_method: VerificationMethod | None = None
    owner: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    title: str | None = None
    statement: str | None = None
    rationale: str | None = None
    acceptance_criteria: str | None = None
    comment: str | None = None
    relations: list[Relation] | None = None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for tag in value:
            if "," in tag or "\n" in tag or "\r" in tag:
                raise ValueError("Tags must not contain commas or line breaks")
        normalized = [tag.strip() for tag in value if tag.strip()]
        return list(dict.fromkeys(normalized))


class RequirementCreate(RequirementBase):
    """Payload for creating a requirement in a managed document."""

    document: str
    uid: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    type: RequirementType
    status: RequirementStatus
    priority: RequirementPriority
    verification_method: VerificationMethod
    owner: str
    title: str
    statement: str
    acceptance_criteria: str
    revision: str | None = None


class RequirementUpdate(RequirementBase):
    """Partial update payload; body or If-Match supplies optimistic revision."""

    revision: str | None = None


class Requirement(BaseModel):
    """Normalized requirement returned by the native JSON adapter."""

    model_config = ConfigDict(extra="forbid")
    uid: str
    mid: str
    document: str
    document_path: str = ""
    section_path: list[str] = Field(default_factory=list)
    document_title: str
    node_type: str
    toc: str | None = None
    type: RequirementType | None = None
    status: RequirementStatus | None = None
    priority: RequirementPriority | None = None
    verification_method: VerificationMethod | None = None
    owner: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    title: str | None = None
    statement: str | None = None
    rationale: str | None = None
    acceptance_criteria: str | None = None
    comment: str | None = None
    relations: list[Relation] = Field(default_factory=list)
    extra_fields: dict[str, Any] = Field(default_factory=dict)
    revision: str


class RequirementList(BaseModel):
    """Stable envelope for requirement tables."""

    items: list[Requirement]
    total: int
    revision: str


class ValidationResult(BaseModel):
    """Native StrictDoc validation result."""

    valid: bool
    revision: str
    diagnostics: list[Diagnostic]
    duration_ms: int


class NativeCommandResult(BaseModel):
    """Result of one subprocess invocation without shell interpretation."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


class ExportFile(BaseModel):
    """Generated export artifact metadata."""

    id: str
    name: str
    path: str
    sha256: str
    size: int
    media_type: str


class ExportJob(BaseModel):
    """Synchronous native StrictDoc export represented as a job."""

    id: str
    format: Literal["html", "pdf", "excel", "json", "reqif", "combined-html"]
    status: Literal["running", "succeeded", "failed"]
    command: list[str] = Field(default_factory=list)
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    created_files: list[ExportFile] = Field(default_factory=list)
    error: str | None = None
    revision: str
