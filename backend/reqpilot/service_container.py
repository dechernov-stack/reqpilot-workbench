"""Application service container shared by FastAPI routers."""

from __future__ import annotations

from dataclasses import dataclass

from reqpilot.config import ProjectConfig
from reqpilot.export_service import StrictDocExportService
from reqpilot.strictdoc_adapter import StrictDocAdapter
from reqpilot.strictdoc_writer import SafeStrictDocWriter


@dataclass(frozen=True)
class Services:
    """Explicit dependency container without global mutable domain state."""

    config: ProjectConfig
    strictdoc: StrictDocAdapter
    writer: SafeStrictDocWriter
    exports: StrictDocExportService


def build_services(config: ProjectConfig) -> Services:
    """Construct the application's backend services."""

    adapter = StrictDocAdapter(config)
    return Services(
        config=config,
        strictdoc=adapter,
        writer=SafeStrictDocWriter(adapter),
        exports=StrictDocExportService(adapter),
    )
