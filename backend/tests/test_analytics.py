"""Unified graph, matrix, impact, dashboard, API, and scale tests."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.git_adapter import GitAdapter
from reqpilot.adapters.trace_links import TraceLinkRepository
from reqpilot.analytics_models import (
    ArchitectureRelation,
    CapellaElement,
    CapellaIndex,
    SourceKind,
)
from reqpilot.models import Relation, Requirement
from reqpilot.routers.analytics import create_analytics_router
from reqpilot.routers.capella import create_capella_router
from reqpilot.routers.trace_links import create_trace_links_router
from reqpilot.services.dashboard import DashboardService
from reqpilot.services.graph import GraphService, capella_node_id, requirement_node_id
from reqpilot.services.impact import ImpactService
from reqpilot.services.matrices import MatrixService

from tests.analytics_support import analytics_stack, requirement


def services(
    tmp_path: Path, source_repo: Path
) -> tuple[
    list[Requirement],
    CapellaAdapter,
    TraceLinkRepository,
    GraphService,
    MatrixService,
    ImpactService,
    DashboardService,
]:
    """Build the complete isolated analytics service set."""

    config, requirements, capella, links = analytics_stack(tmp_path, source_repo)
    provider = lambda: requirements  # noqa: E731 -- named local dependency callback.
    graph = GraphService(provider, capella, links)
    matrices = MatrixService(provider, capella, links)
    impact = ImpactService(graph, links)
    dashboard = DashboardService(
        provider,
        capella,
        links,
        matrices,
        git=GitAdapter(config.repo_root),
    )
    return requirements, capella, links, graph, matrices, impact, dashboard


def test_graph_filters_focus_path_and_cycle_protection(tmp_path: Path, source_repo: Path) -> None:
    requirements, capella, links, _, _, _, _ = services(tmp_path, source_repo)
    requirements.extend(
        [
            requirement(
                "CYCLE-A", "System", relations=[Relation(value="CYCLE-B", role="DependsOn")]
            ),
            requirement(
                "CYCLE-B", "System", relations=[Relation(value="CYCLE-A", role="DependsOn")]
            ),
        ]
    )
    graph = GraphService(lambda: requirements, capella, links)
    focused = graph.build(focus="CYCLE-A", depth=4)
    assert {node.uid for node in focused.nodes if node.uid} == {"CYCLE-A", "CYCLE-B"}
    assert len(focused.edges) == 2

    alarm_manager = "30000000-0000-4000-8000-000000000312"
    result = graph.build(
        focus="SYS-002",
        depth=3,
        path_from="SYS-002",
        path_to=alarm_manager,
    )
    assert result.path is not None
    assert result.path.node_ids == [
        requirement_node_id("SYS-002"),
        capella_node_id("20000000-0000-4000-8000-000000000213"),
        capella_node_id(alarm_manager),
    ]
    strictdoc_only = graph.build(sources={"strictdoc"}, types={"Safety"})
    assert {node.uid for node in strictdoc_only.nodes} == {"SAF-001", "SAF-002"}
    diagrams = graph.build(types={"Diagram"})
    assert len(diagrams.nodes) == 3


def test_all_four_matrices_coverage_and_csv(tmp_path: Path, source_repo: Path) -> None:
    _, _, _, _, matrices, _, _ = services(tmp_path, source_repo)
    tests = matrices.requirements_tests()
    functions = matrices.requirements_functions()
    components = matrices.requirements_components()
    allocations = matrices.functions_components()
    assert tests.coverage.percent == 100
    assert len(tests.cells) == 6
    assert functions.cells
    assert components.cells
    assert len(allocations.cells) == 7
    assert allocations.coverage.percent == 70
    csv_value = matrices.to_csv(functions)
    assert csv_value.startswith("Требования ↔ функции,")
    assert "SYS-002" in csv_value


def test_impact_returns_groups_and_concrete_shortest_paths(
    tmp_path: Path, source_repo: Path
) -> None:
    _, _, _, _, _, impact, _ = services(tmp_path, source_repo)
    requirement_result = impact.for_requirement("SYS-002", depth=3)
    keys = {group.key for group in requirement_result.groups}
    assert {"tests", "functions", "components", "diagrams"} <= keys
    assert all(
        path.node_ids[0] == requirement_node_id("SYS-002") for path in requirement_result.paths
    )

    capella_result = impact.for_capella("30000000-0000-4000-8000-000000000312", depth=3)
    capella_keys = {group.key for group in capella_result.groups}
    assert "allocations" in capella_keys
    assert "requirements" in capella_keys
    assert "tests" in capella_keys


def test_dashboard_reports_fixture_and_exact_coverage(tmp_path: Path, source_repo: Path) -> None:
    _, _, _, _, _, _, dashboard = services(tmp_path, source_repo)
    result = dashboard.snapshot()
    assert result.requirements == 17
    assert result.capella_elements == 37
    assert result.trace_links == 10
    assert result.broken_links == 0
    assert result.test_coverage.percent == 100
    assert result.architecture_coverage.percent == 100
    assert result.fixture_banner == "Демо-архитектура, не загруженная из Capella"


def test_factory_routers_expose_contract_and_csv(tmp_path: Path, source_repo: Path) -> None:
    _, capella, links, graph, matrices, impact, dashboard = services(tmp_path, source_repo)
    app = FastAPI()
    app.include_router(create_capella_router(capella))
    app.include_router(create_trace_links_router(links))
    app.include_router(create_analytics_router(graph, matrices, impact, dashboard))
    with TestClient(app) as client:
        status = client.get("/api/capella/status")
        assert status.status_code == 200
        assert status.json()["fixture"] is True
        assert client.get("/api/capella/elements", params={"layer": "LA"}).json()["total"] == 6
        svg = client.get("/api/capella/diagrams/90000000-0000-4000-8000-000000000003/svg")
        assert svg.status_code == 200
        assert svg.headers["content-type"].startswith("image/svg+xml")
        trace_listing = client.get("/api/trace-links").json()
        assert trace_listing["total"] == 10
        assert client.post("/api/trace-links/validate").json()["valid"] is True
        updated = client.put(
            "/api/trace-links/TL-0001",
            headers={"If-Match": trace_listing["revision"]},
            json={"rationale": "Updated through an If-Match-only request."},
        )
        assert updated.status_code == 200
        assert updated.json()["id"] == "TL-0001"
        graph_response = client.get("/api/graph", params={"focus": "SYS-002", "depth": 2})
        assert graph_response.status_code == 200
        assert graph_response.json()["nodes"]
        matrix = client.get("/api/matrices/requirements-functions", params={"format": "csv"})
        assert matrix.status_code == 200
        assert matrix.headers["content-type"].startswith("text/csv")
        assert client.get("/api/impact/requirement/SYS-002").status_code == 200
        assert client.get("/api/dashboard").json()["trace_links"] == 10


class _SyntheticCapella:
    def __init__(self, index: CapellaIndex) -> None:
        self.index = index

    def ensure_loaded(self) -> CapellaIndex:
        return self.index


class _EmptyLinks:
    def list_links(self) -> SimpleNamespace:
        return SimpleNamespace(items=[])


def test_graph_scale_300_requirements_1000_elements_2000_edges_under_one_second() -> None:
    requirements = [requirement(f"PERF-{index:03d}", "System") for index in range(300)]
    elements = [
        CapellaElement(
            uuid=f"perf-{index:04d}",
            model_id="performance",
            type="SystemFunction",
            layer="SA",
            name=f"Function {index:04d}",
            path=["Performance", f"Function {index:04d}"],
        )
        for index in range(1000)
    ]
    relations = [
        ArchitectureRelation(
            source_uuid=f"perf-{index % 1000:04d}",
            target_uuid=f"perf-{(index + 1) % 1000:04d}",
            type=f"edge-{index // 1000}",
        )
        for index in range(2000)
    ]
    index = CapellaIndex(
        model_id="performance",
        source_kind=SourceKind.FIXTURE,
        source_label="synthetic performance test",
        fingerprint="test",
        elements=elements,
        relations=relations,
    )
    graph = GraphService(
        lambda: requirements,
        cast(Any, _SyntheticCapella(index)),
        cast(Any, _EmptyLinks()),
    )
    started = time.perf_counter()
    result = graph.build(max_nodes=5000)
    duration = time.perf_counter() - started
    assert result.total_nodes == 1300
    assert result.total_edges == 2000
    assert duration < 1.0
