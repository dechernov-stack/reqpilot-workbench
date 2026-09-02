"""Native StrictDoc export endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from reqpilot.dependencies import get_services
from reqpilot.export_service import ExportFormat
from reqpilot.models import ExportJob
from reqpilot.service_container import Services

router = APIRouter(prefix="/api/exports", tags=["exports"])
ServicesDep = Annotated[Services, Depends(get_services)]


def _run(export_format: ExportFormat, services: Services) -> ExportJob:
    return services.exports.run(export_format)


@router.post("/strictdoc/html")
def export_html(services: ServicesDep) -> ExportJob:
    """Run StrictDoc's native standalone-capable HTML export."""

    return _run("html", services)


@router.post("/strictdoc/pdf")
def export_pdf(services: ServicesDep) -> ExportJob:
    """Run StrictDoc's native PDF export and expose failures verbatim."""

    return _run("pdf", services)


@router.post("/strictdoc/excel")
def export_excel(services: ServicesDep) -> ExportJob:
    """Run StrictDoc's native Excel export."""

    return _run("excel", services)


@router.post("/strictdoc/json")
def export_json(services: ServicesDep) -> ExportJob:
    """Run StrictDoc's native JSON export."""

    return _run("json", services)


@router.post("/strictdoc/reqif")
def export_reqif(services: ServicesDep) -> ExportJob:
    """Run StrictDoc's native ReqIF exporter with MID identifiers enabled."""

    return _run("reqif", services)


@router.get("/jobs/{job_id}")
def get_export_job(job_id: str, services: ServicesDep) -> ExportJob:
    """Return synchronous export status and native stdout/stderr."""

    return services.exports.get_job(job_id)


@router.get("/files/{file_id}", response_class=FileResponse)
def get_export_file(file_id: str, services: ServicesDep) -> FileResponse:
    """Download a known contained export artifact by opaque ID."""

    path, media_type = services.exports.get_file(file_id)
    return FileResponse(path=path, media_type=media_type, filename=path.name)
