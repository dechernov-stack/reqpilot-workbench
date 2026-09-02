"""System health, project metadata, diagnostics, and reload endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from reqpilot.dependencies import get_services
from reqpilot.service_container import Services
from reqpilot.strictdoc_adapter import PINNED_STRICTDOC_VERSION

router = APIRouter(prefix="/api", tags=["system"])
ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("/health")
def health(services: ServicesDep) -> dict[str, Any]:
    """Report the health of the canonical StrictDoc source."""

    listing = services.strictdoc.list_requirements()
    version = services.strictdoc.version
    return {
        "status": "ok" if version == PINNED_STRICTDOC_VERSION else "error",
        "strictdoc_version": version,
        "required_strictdoc_version": PINNED_STRICTDOC_VERSION,
        "revision": listing.revision,
        "requirements": listing.total,
    }


@router.get("/project")
def project(services: ServicesDep) -> dict[str, Any]:
    """Expose safe, UI-relevant project configuration and source boundaries."""

    config = services.config
    return {
        "id": config.project.id,
        "title": config.project.title,
        "schema_version": config.schema_version,
        "server": config.server.model_dump(),
        "strictdoc": {
            "root": config.strictdoc.root,
            "managed_documents": config.strictdoc.managed_documents,
            "export_root": config.strictdoc.export_root,
            "source_of_truth": True,
        },
        "capella": {
            "mode": config.capella.mode,
            "read_only": config.capella.read_only,
        },
        "fixture": config.fixture.model_dump(),
    }


@router.get("/diagnostics")
def diagnostics(services: ServicesDep) -> dict[str, Any]:
    """Return structured diagnostics without hiding native command failures."""

    adapter = services.strictdoc
    listing = adapter.list_requirements()
    return {
        "revision": listing.revision,
        "strictdoc": {
            "version": adapter.version,
            "diagnostics": [item.model_dump(mode="json") for item in adapter.diagnostics],
            "last_command": (
                adapter.last_command.model_dump(mode="json")
                if adapter.last_command is not None
                else None
            ),
            "last_refresh_epoch": adapter.last_refresh_epoch,
            "cache_path": adapter.cache_path.relative_to(services.config.repo_root).as_posix(),
        },
    }


@router.post("/reload")
def reload_project(services: ServicesDep) -> dict[str, Any]:
    """Re-run the native JSON export and replace only the derived cache."""

    listing = services.strictdoc.refresh()
    return {"status": "reloaded", **listing.model_dump(mode="json")}
