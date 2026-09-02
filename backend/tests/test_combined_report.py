"""Standalone combined HTML report tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.trace_links import TraceLinkRepository
from reqpilot.config import load_project_config
from reqpilot.services.combined_report import CombinedReportService
from reqpilot.strictdoc_adapter import StrictDocAdapter


def _report_service(tmp_path: Path, source_repo: Path) -> CombinedReportService:
    shutil.copytree(source_repo / "requirements", tmp_path / "requirements")
    shutil.copytree(source_repo / "fixtures", tmp_path / "fixtures")
    shutil.copy2(source_repo / "trace-links.yaml", tmp_path / "trace-links.yaml")
    shutil.copy2(source_repo / "deleted-uids.json", tmp_path / "deleted-uids.json")
    shutil.copy2(source_repo / "project.yaml", tmp_path / "project.yaml")
    config = load_project_config(tmp_path / "project.yaml")
    strictdoc = StrictDocAdapter(config)
    capella = CapellaAdapter(config)
    links = TraceLinkRepository(
        config,
        lambda: strictdoc.list_requirements().items,
        capella,
    )
    return CombinedReportService(config, strictdoc, capella, links)


def test_combined_report_is_standalone_and_source_grounded(
    tmp_path: Path,
    source_repo: Path,
) -> None:
    service = _report_service(tmp_path, source_repo)
    result = service.run()
    report = (tmp_path / result.path).read_text(encoding="utf-8")

    assert result.requirement_count == 24
    assert result.trace_link_count == 10
    assert result.broken_link_count == 0
    assert result.test_coverage == 100.0
    assert "Демо-архитектура, не загруженная из Capella" in report
    assert "SYS-002" in report
    assert "Evaluate Pressure Threshold" in report
    assert 'src="data:image/svg+xml;base64,' in report
    assert "<script" not in report.casefold()
    assert "https://" not in report.casefold()
    assert "http://" not in report.casefold()


def test_combined_report_rejects_output_outside_export_root(
    tmp_path: Path,
    source_repo: Path,
) -> None:
    service = _report_service(tmp_path, source_repo)
    with pytest.raises(ValueError, match="escapes"):
        service.run(tmp_path / "outside.html")


def test_combined_report_rejects_symlinked_output_directory(
    tmp_path: Path,
    source_repo: Path,
) -> None:
    service = _report_service(tmp_path, source_repo)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-combined"
    outside.mkdir()
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "combined").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        service.run()

    assert list(outside.iterdir()) == []


def test_combined_export_api_registers_download(client: TestClient) -> None:
    response = client.post("/api/exports/combined-html")
    assert response.status_code == 200
    job = response.json()
    assert job["format"] == "combined-html"
    assert job["status"] == "succeeded"
    assert job["command"] == []
    assert job["returncode"] == 0
    assert len(job["created_files"]) == 1

    download = client.get(f"/api/exports/files/{job['created_files'][0]['id']}")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/html")
    assert "SYS-002" in download.text
