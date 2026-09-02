"""FastAPI application factory for the local-only ReqPilot backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from reqpilot import __version__
from reqpilot.analytics_container import AnalyticsServices, build_analytics_services
from reqpilot.config import ProjectConfig, load_project_config
from reqpilot.errors import ReqPilotError
from reqpilot.routers import analytics, capella, exports, requirements, system, trace_links
from reqpilot.routers.combined_export import create_combined_export_router
from reqpilot.service_container import Services, build_services
from reqpilot.services.combined_report import CombinedReportService


def _safe_frontend_entry(repo_root: Path, path: Path, *, directory: bool) -> Path | None:
    """Return one existing frontend path without following any symlink component."""

    root = repo_root.resolve(strict=True)
    try:
        relative = path.absolute().relative_to(root)
    except ValueError:
        return None
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if directory:
        return resolved if resolved.is_dir() else None
    return resolved if resolved.is_file() else None


def create_app(
    *,
    config_path: Path | None = None,
    config: ProjectConfig | None = None,
    services: Services | None = None,
    analytics_services: AnalyticsServices | None = None,
) -> FastAPI:
    """Create one isolated app instance with no global mutable domain state."""

    if config is None:
        selected = config_path or Path(os.environ.get("REQPILOT_CONFIG", "project.yaml"))
        config = load_project_config(selected)
    application = FastAPI(
        title="ReqPilot Engineering Workbench",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "[::1]", "localhost", "testserver"],
    )
    application.state.services = services or build_services(config)
    application.state.analytics = analytics_services or build_analytics_services(
        config,
        application.state.services.strictdoc,
    )

    @application.exception_handler(ReqPilotError)
    async def reqpilot_error_handler(_request: Request, error: ReqPilotError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.as_detail()})

    application.include_router(system.router)
    application.include_router(requirements.router)
    application.include_router(exports.router)
    analytics_slice = application.state.analytics
    application.include_router(capella.create_capella_router(analytics_slice.capella))
    application.include_router(trace_links.create_trace_links_router(analytics_slice.trace_links))
    application.include_router(
        analytics.create_analytics_router(
            analytics_slice.graph,
            analytics_slice.matrices,
            analytics_slice.impact,
            analytics_slice.dashboard,
        )
    )
    combined = CombinedReportService(
        config,
        application.state.services.strictdoc,
        analytics_slice.capella,
        analytics_slice.trace_links,
    )
    application.include_router(
        create_combined_export_router(combined, application.state.services.exports)
    )

    frontend_dist = _safe_frontend_entry(
        config.repo_root,
        config.repo_root / "frontend" / "dist",
        directory=True,
    )
    frontend_index = (
        _safe_frontend_entry(config.repo_root, frontend_dist / "index.html", directory=False)
        if frontend_dist is not None
        else None
    )
    frontend_assets = (
        _safe_frontend_entry(config.repo_root, frontend_dist / "assets", directory=True)
        if frontend_dist is not None
        else None
    )
    if frontend_index is not None and frontend_dist is not None:
        if frontend_assets is not None:
            application.mount(
                "/assets",
                StaticFiles(directory=frontend_assets),
                name="frontend-assets",
            )

        @application.get("/", include_in_schema=False, response_class=FileResponse)
        def root_frontend() -> FileResponse:
            return FileResponse(frontend_index)

        @application.get("/{frontend_path:path}", include_in_schema=False)
        def frontend_route(frontend_path: str) -> FileResponse:
            candidate = _safe_frontend_entry(
                frontend_dist,
                frontend_dist / frontend_path,
                directory=False,
            )
            return FileResponse(candidate if candidate is not None else frontend_index)

    else:

        @application.get("/", include_in_schema=False)
        def root_placeholder() -> dict[str, Any]:
            return {
                "name": "ReqPilot Engineering Workbench",
                "api": "/api/docs",
                "status": "/api/health",
            }

    return application


app = create_app()
