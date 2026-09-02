"""Composition root for the optional Capella/traceability analytics slice."""

from __future__ import annotations

from dataclasses import dataclass

from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.git_adapter import GitAdapter
from reqpilot.adapters.trace_links import TraceLinkRepository
from reqpilot.config import ProjectConfig
from reqpilot.models import Requirement
from reqpilot.services.dashboard import DashboardService
from reqpilot.services.graph import GraphService
from reqpilot.services.impact import ImpactService
from reqpilot.services.matrices import MatrixService
from reqpilot.strictdoc_adapter import StrictDocAdapter


@dataclass(frozen=True)
class AnalyticsServices:
    """Explicit dependencies for Stage 3-5 routers."""

    capella: CapellaAdapter
    trace_links: TraceLinkRepository
    graph: GraphService
    matrices: MatrixService
    impact: ImpactService
    dashboard: DashboardService


def build_analytics_services(
    config: ProjectConfig,
    strictdoc: StrictDocAdapter,
) -> AnalyticsServices:
    """Build Stage 3-5 services using StrictDoc's derived requirement listing."""

    def requirement_provider() -> list[Requirement]:
        return strictdoc.list_requirements().items

    capella = CapellaAdapter(config)
    trace_links = TraceLinkRepository(config, requirement_provider, capella)
    graph = GraphService(requirement_provider, capella, trace_links)
    matrices = MatrixService(requirement_provider, capella, trace_links)
    impact = ImpactService(graph, trace_links)
    dashboard = DashboardService(
        requirement_provider,
        capella,
        trace_links,
        matrices,
        git=GitAdapter(config.repo_root),
    )
    return AnalyticsServices(
        capella=capella,
        trace_links=trace_links,
        graph=graph,
        matrices=matrices,
        impact=impact,
        dashboard=dashboard,
    )
