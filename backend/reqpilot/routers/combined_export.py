"""Combined standalone HTML export endpoint."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter

from reqpilot.export_service import StrictDocExportService
from reqpilot.models import ExportJob
from reqpilot.services.combined_report import CombinedReportService


def create_combined_export_router(
    report_service: CombinedReportService,
    export_service: StrictDocExportService,
) -> APIRouter:
    """Create a router closed over explicit derived-export dependencies."""

    router = APIRouter(prefix="/api/exports", tags=["exports"])

    @router.post("/combined-html")
    def export_combined_html() -> ExportJob:
        """Generate and register an offline combined engineering report."""

        job_id = uuid.uuid4().hex
        revision = report_service.strictdoc.revision
        started = time.monotonic()
        try:
            result = report_service.run()
            path = report_service.config.repo_root / result.path
            artifact = export_service.register_artifact(path)
            job = ExportJob(
                id=job_id,
                format="combined-html",
                status="succeeded",
                command=[],
                returncode=0,
                stdout=(
                    f"Standalone combined HTML generated: {result.path}; SHA-256 {result.sha256}"
                ),
                duration_ms=int((time.monotonic() - started) * 1000),
                created_files=[artifact],
                revision=revision,
            )
        except Exception as error:
            job = ExportJob(
                id=job_id,
                format="combined-html",
                status="failed",
                command=[],
                returncode=1,
                stderr=str(error),
                duration_ms=int((time.monotonic() - started) * 1000),
                error=str(error),
                revision=revision,
            )
        return export_service.record_job(job)

    return router
