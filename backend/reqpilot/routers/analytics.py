"""Factory for dashboard, graph, matrix, and impact endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Response

from reqpilot.analytics_models import DashboardResult, GraphResult, ImpactResult, MatrixResult
from reqpilot.services.dashboard import DashboardService
from reqpilot.services.graph import GraphService, filter_values
from reqpilot.services.impact import ImpactService
from reqpilot.services.matrices import MatrixService


def create_analytics_router(
    graph: GraphService,
    matrices: MatrixService,
    impact: ImpactService,
    dashboard: DashboardService,
) -> APIRouter:
    """Create analytics endpoints bound to framework-independent services."""

    router = APIRouter(prefix="/api", tags=["analytics"])

    @router.get("/dashboard")
    def dashboard_snapshot() -> DashboardResult:
        return dashboard.snapshot()

    @router.get("/graph")
    def unified_graph(
        focus: str | None = None,
        depth: int = Query(default=2, ge=1, le=4),
        sources: str | None = None,
        types: str | None = None,
        relations: str | None = None,
        text: str | None = None,
        path_from: str | None = None,
        path_to: str | None = None,
        max_nodes: int = Query(default=500, ge=1, le=5000),
    ) -> GraphResult:
        return graph.build(
            focus=focus,
            depth=depth,
            sources=filter_values(sources),
            types=filter_values(types),
            relations=filter_values(relations),
            text=text,
            path_from=path_from,
            path_to=path_to,
            max_nodes=max_nodes,
        )

    def matrix_response(matrix: MatrixResult, output: Literal["json", "csv"]) -> object:
        if output == "csv":
            return Response(
                content=matrices.to_csv(matrix),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{matrix.id}.csv"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return matrix

    @router.get("/matrices/requirements-tests", response_model=None)
    def requirements_tests(
        text: str | None = None,
        output: Literal["json", "csv"] = Query(default="json", alias="format"),
    ) -> object:
        return matrix_response(matrices.requirements_tests(text=text), output)

    @router.get("/matrices/requirements-functions", response_model=None)
    def requirements_functions(
        text: str | None = None,
        output: Literal["json", "csv"] = Query(default="json", alias="format"),
    ) -> object:
        return matrix_response(matrices.requirements_functions(text=text), output)

    @router.get("/matrices/requirements-components", response_model=None)
    def requirements_components(
        text: str | None = None,
        output: Literal["json", "csv"] = Query(default="json", alias="format"),
    ) -> object:
        return matrix_response(matrices.requirements_components(text=text), output)

    @router.get("/matrices/functions-components", response_model=None)
    def functions_components(
        text: str | None = None,
        output: Literal["json", "csv"] = Query(default="json", alias="format"),
    ) -> object:
        return matrix_response(matrices.functions_components(text=text), output)

    @router.get("/impact/requirement/{uid}")
    def requirement_impact(
        uid: str,
        depth: int = Query(default=3, ge=1, le=4),
    ) -> ImpactResult:
        return impact.for_requirement(uid, depth=depth)

    @router.get("/impact/capella/{uuid}")
    def capella_impact(
        uuid: str,
        depth: int = Query(default=3, ge=1, le=4),
    ) -> ImpactResult:
        return impact.for_capella(uuid, depth=depth)

    return router
