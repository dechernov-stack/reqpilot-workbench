"""Factory for the read-only Capella REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response

from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.analytics_models import CapellaElement, CapellaStatus


def create_capella_router(adapter: CapellaAdapter) -> APIRouter:
    """Create a router bound to one configured read-only Capella adapter."""

    router = APIRouter(prefix="/api/capella", tags=["capella"])

    @router.get("/status")
    def status() -> CapellaStatus:
        return adapter.status()

    @router.post("/reload")
    def reload_capella() -> CapellaStatus:
        adapter.reload()
        return adapter.status()

    @router.get("/elements")
    def elements(
        layer: str | None = None,
        type_filter: str | None = Query(default=None, alias="type"),
        text: str | None = None,
        parent_uuid: str | None = None,
        related_to: str | None = None,
    ) -> dict[str, object]:
        items = adapter.list_elements(
            layer=layer,
            type_=type_filter,
            text=text,
            parent_uuid=parent_uuid,
            related_to=related_to,
        )
        status_value = adapter.status()
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "total": len(items),
            "fingerprint": status_value.fingerprint,
            "fixture": status_value.fixture,
            "banner": status_value.banner,
        }

    @router.get("/elements/{uuid}")
    def element(uuid: str) -> CapellaElement:
        return adapter.get_element(uuid)

    @router.get("/diagrams")
    def diagrams() -> dict[str, object]:
        items = adapter.list_diagrams()
        status_value = adapter.status()
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "total": len(items),
            "fixture": status_value.fixture,
            "banner": status_value.banner,
        }

    @router.get("/diagrams/{uuid}/svg", response_class=Response)
    def diagram_svg(uuid: str) -> Response:
        svg = adapter.render_diagram(uuid)
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
