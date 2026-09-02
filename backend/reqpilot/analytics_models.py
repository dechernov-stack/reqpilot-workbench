"""Domain models shared by the Capella, traceability, and analytics services.

These models are intentionally independent from FastAPI.  They describe derived
views only; canonical requirements remain in StrictDoc, architecture remains in
Capella, and cross-tool links remain in ``trace-links.yaml``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FIXTURE_BANNER = "Демо-архитектура, не загруженная из Capella"


class CapellaState(StrEnum):
    """Stable states exposed by the read-only Capella adapter."""

    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    LOADING = "loading"
    READY = "ready"
    STALE = "stale"
    ERROR = "error"
    FIXTURE = "fixture"


class SourceKind(StrEnum):
    """Architecture index provenance."""

    LIVE = "live"
    FIXTURE = "fixture"


class CapellaElement(BaseModel):
    """Normalized, read-only Capella element."""

    model_config = ConfigDict(extra="forbid")

    uuid: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    layer: Literal["OA", "SA", "LA", "PA", "EPBS", "OTHER"] = "OTHER"
    name: str
    description: str | None = None
    path: list[str] = Field(default_factory=list)
    parent_uuid: str | None = None
    related_element_uuids: list[str] = Field(default_factory=list)
    diagram_uuids: list[str] = Field(default_factory=list)

    @field_validator("related_element_uuids", "diagram_uuids")
    @classmethod
    def unique_sorted_ids(cls, value: list[str]) -> list[str]:
        """Keep identifier lists deterministic and duplicate-free."""

        return sorted(set(value))


class ArchitectureRelation(BaseModel):
    """Directed relationship between two architecture elements."""

    model_config = ConfigDict(extra="forbid")

    source_uuid: str = Field(min_length=1)
    target_uuid: str = Field(min_length=1)
    type: str = Field(min_length=1)
    name: str | None = None


class CapellaDiagram(BaseModel):
    """Diagram metadata; SVG content is loaded only through a dedicated call."""

    model_config = ConfigDict(extra="forbid")

    uuid: str = Field(min_length=1)
    name: str
    type: str = "Diagram"
    description: str | None = None
    represented_element_uuids: list[str] = Field(default_factory=list)
    svg_available: bool = True
    svg: str | None = Field(default=None, exclude=True)

    @field_validator("represented_element_uuids")
    @classmethod
    def unique_sorted_ids(cls, value: list[str]) -> list[str]:
        """Keep represented-element lists stable."""

        return sorted(set(value))


class CapellaIndex(BaseModel):
    """Derived architecture index produced by fixture parsing or the live worker."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    model_id: str
    source_kind: SourceKind
    source_label: str
    fingerprint: str
    elements: list[CapellaElement] = Field(default_factory=list)
    relations: list[ArchitectureRelation] = Field(default_factory=list)
    diagrams: list[CapellaDiagram] = Field(default_factory=list)
    indexed_duration_ms: int = Field(default=0, ge=0)


class CapellaStatus(BaseModel):
    """Operational status and explicit source provenance for UI/API consumers."""

    state: CapellaState
    mode: Literal["disabled", "live", "fixture"]
    read_only: Literal[True] = True
    message: str
    model_id: str | None = None
    fingerprint: str | None = None
    element_count: int = 0
    relation_count: int = 0
    diagram_count: int = 0
    indexed_duration_ms: int | None = None
    fixture: bool = False
    banner: str | None = None


class RequirementRef(BaseModel):
    """Stable StrictDoc side of a cross-tool trace link."""

    model_config = ConfigDict(extra="forbid")

    uid: str = Field(min_length=1)
    mid: str = Field(min_length=1)


class ArchitectureRef(BaseModel):
    """Stable UUID-based architecture side of a trace link."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1)
    uuid: str = Field(min_length=1)
    type: str = Field(min_length=1)
    name_snapshot: str


TraceRelation = Literal[
    "satisfied_by",
    "allocated_to",
    "implemented_by",
    "constrains",
    "verified_by",
    "related_to",
]


class TraceLink(BaseModel):
    """Canonical record persisted in ``trace-links.yaml``."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^TL-[0-9]{4,}$")
    requirement: RequirementRef
    architecture: ArchitectureRef
    relation: TraceRelation
    rationale: str
    created_at: datetime
    updated_at: datetime


class TraceLinkCreate(BaseModel):
    """Trace-link create payload; IDs and timestamps are server-owned."""

    model_config = ConfigDict(extra="forbid")

    requirement: RequirementRef
    architecture: ArchitectureRef
    relation: TraceRelation
    rationale: str
    revision: str | None = None


class TraceLinkUpdate(BaseModel):
    """Trace-link update payload; body or If-Match supplies the revision."""

    model_config = ConfigDict(extra="forbid")

    requirement: RequirementRef | None = None
    architecture: ArchitectureRef | None = None
    relation: TraceRelation | None = None
    rationale: str | None = None
    revision: str | None = None


class TraceLinkView(TraceLink):
    """Resolved trace link with non-canonical health metadata."""

    status: Literal[
        "valid",
        "broken_requirement",
        "broken_architecture",
        "architecture_unavailable",
    ]
    current_name: str | None = None
    snapshot_stale: bool = False


class TraceLinkList(BaseModel):
    """Deterministic trace-link listing."""

    items: list[TraceLinkView]
    total: int
    revision: str


class LinkDiagnostic(BaseModel):
    """One actionable trace-link validation finding."""

    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    link_id: str | None = None


class TraceValidationResult(BaseModel):
    """Trace-link validation result."""

    valid: bool
    revision: str
    diagnostics: list[LinkDiagnostic] = Field(default_factory=list)


class GraphNode(BaseModel):
    """Unified graph node."""

    id: str
    source: Literal["strictdoc", "capella", "placeholder"]
    type: str
    label: str
    uid: str | None = None
    uuid: str | None = None
    group: str
    broken: bool = False
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Unified graph edge."""

    id: str
    source: str
    target: str
    relation: str
    origin: Literal["strictdoc", "capella", "trace-link"]
    directed: bool = True
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class GraphPath(BaseModel):
    """Concrete shortest path through the unified graph."""

    node_ids: list[str]
    edge_ids: list[str]
    length: int = Field(ge=0)


class GraphResult(BaseModel):
    """Filtered unified graph plus optional shortest path."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int
    total_edges: int
    truncated: bool = False
    path: GraphPath | None = None


class MatrixAxisItem(BaseModel):
    """Row/column descriptor for a sparse traceability matrix."""

    id: str
    label: str
    type: str


class MatrixCell(BaseModel):
    """Non-empty sparse matrix cell."""

    row_id: str
    column_id: str
    relations: list[str]
    link_ids: list[str] = Field(default_factory=list)


class Coverage(BaseModel):
    """Coverage fraction with exact numerator/denominator."""

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)


class MatrixResult(BaseModel):
    """Sparse matrix response suitable for virtualization."""

    id: str
    title: str
    rows: list[MatrixAxisItem]
    columns: list[MatrixAxisItem]
    cells: list[MatrixCell]
    coverage: Coverage


class ImpactGroup(BaseModel):
    """Impact nodes grouped by source/domain type."""

    key: str
    label: str
    nodes: list[GraphNode]


class ImpactResult(BaseModel):
    """Deterministic impact analysis with named shortest paths."""

    focus: GraphNode
    depth: int
    groups: list[ImpactGroup]
    paths: list[GraphPath]
    broken_links: list[str]


class DashboardResult(BaseModel):
    """Derived project summary shown by the dashboard."""

    requirements: int
    capella_elements: int
    internal_relations: int
    trace_links: int
    test_coverage: Coverage
    architecture_coverage: Coverage
    broken_links: int
    capella_status: CapellaStatus
    fixture_banner: str | None = None
    indexing_duration_ms: int | None = None
    git_status: str
    last_export: str | None = None
    uncovered_test_requirements: list[str] = Field(default_factory=list)
    uncovered_architecture_requirements: list[str] = Field(default_factory=list)
    recent_errors: list[str] = Field(default_factory=list)
