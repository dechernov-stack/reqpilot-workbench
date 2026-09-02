"""FastAPI contracts and native export integration tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from reqpilot.app import create_app
from reqpilot.config import load_project_config
from reqpilot.errors import NotFoundError, PathSecurityError
from reqpilot.export_service import StrictDocExportService
from reqpilot.models import NativeCommandResult
from reqpilot.service_container import Services
from reqpilot.strictdoc_adapter import StrictDocAdapter


def test_system_and_requirement_read_contracts(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["strictdoc_version"] == "0.29.0"
    project = client.get("/api/project")
    assert project.status_code == 200
    assert project.json()["strictdoc"]["source_of_truth"] is True
    listing = client.get("/api/requirements", params={"type": "Safety"})
    assert listing.status_code == 200
    assert set(listing.json()) == {"items", "total", "revision"}
    assert listing.json()["total"] == 2
    single = client.get("/api/requirements/SAF-001")
    assert single.status_code == 200
    assert single.json()["uid"] == "SAF-001"
    assert len(single.json()["revision"]) == 64
    assert client.get("/api/requirements/NOPE").status_code == 404
    diagnostics = client.get("/api/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.json()["strictdoc"]["last_command"]["command"]
    reloaded = client.post("/api/reload")
    assert reloaded.status_code == 200
    assert reloaded.json()["status"] == "reloaded"


def test_host_header_is_restricted_to_loopback(client: TestClient) -> None:
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get("/api/health", headers={"Host": "localhost:8080"}).status_code == 200


def test_api_create_update_delete_and_conflicts(client: TestClient) -> None:
    revision = client.get("/api/requirements").json()["revision"]
    payload = {
        "document": "05_tests.sdoc",
        "uid": "TC-HTTP-001",
        "type": "TestCase",
        "status": "Draft",
        "priority": "Low",
        "verification_method": "Test",
        "owner": "HTTP test",
        "tags": ["http"],
        "title": "HTTP CRUD",
        "statement": "Создать через API.",
        "acceptance_criteria": "Ответ 201.",
        "relations": [{"value": "SYS-001", "role": "Verifies"}],
        "revision": revision,
    }
    created = client.post("/api/requirements", json=payload)
    assert created.status_code == 201, created.text
    created_body = created.json()
    assert created_body["uid"] == "TC-HTTP-001"
    update = client.put(
        "/api/requirements/TC-HTTP-001",
        headers={"If-Match": f'"{created_body["revision"]}"'},
        json={"title": "HTTP CRUD — обновлено"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["mid"] == created_body["mid"]
    assert update.json()["title"].endswith("обновлено")
    assert (
        client.put(
            "/api/requirements/TC-HTTP-001",
            json={"title": "no revision"},
        ).status_code
        == 428
    )
    assert (
        client.put(
            "/api/requirements/TC-HTTP-001",
            headers={"If-Match": "different"},
            json={"revision": update.json()["revision"], "title": "mismatch"},
        ).status_code
        == 400
    )
    stale = client.put(
        "/api/requirements/TC-HTTP-001",
        json={"revision": "0" * 64, "title": "stale"},
    )
    assert stale.status_code == 409
    deleted = client.delete(
        "/api/requirements/TC-HTTP-001",
        params={"revision": update.json()["revision"]},
    )
    assert deleted.status_code == 204
    assert client.get("/api/requirements/TC-HTTP-001").status_code == 404


def test_api_validation_and_pydantic_vocabulary(client: TestClient) -> None:
    validated = client.post("/api/requirements/validate")
    assert validated.status_code == 200
    assert validated.json()["valid"] is True
    revision = validated.json()["revision"]
    invalid = client.post(
        "/api/requirements",
        json={
            "document": "05_tests.sdoc",
            "uid": "TC-BAD-001",
            "type": "MadeUp",
            "status": "Wrong",
            "priority": "Urgent",
            "verification_method": "Guess",
            "owner": "test",
            "title": "bad",
            "statement": "bad",
            "acceptance_criteria": "bad",
            "revision": revision,
        },
    )
    assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("endpoint", "suffix"),
    [
        ("json", ".json"),
        ("excel", ".xlsx"),
        ("reqif", ".reqif"),
        ("html", ".html"),
    ],
)
def test_native_export_jobs_and_downloads(client: TestClient, endpoint: str, suffix: str) -> None:
    response = client.post(f"/api/exports/strictdoc/{endpoint}")
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["format"] == endpoint
    assert job["status"] == "succeeded", job["error"]
    assert isinstance(job["command"], list) and job["command"]
    assert job["returncode"] == 0
    assert job["duration_ms"] >= 0
    artifacts = [item for item in job["created_files"] if item["name"].endswith(suffix)]
    assert artifacts
    artifact = artifacts[0]
    status_response = client.get(f"/api/exports/jobs/{job['id']}")
    assert status_response.status_code == 200
    download = client.get(f"/api/exports/files/{artifact['id']}")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == artifact["sha256"]


def test_export_not_found_and_path_rejection(
    client: TestClient, services: Services, tmp_path: Path
) -> None:
    assert client.get("/api/exports/jobs/not-found").status_code == 404
    assert client.get("/api/exports/files/../../etc/passwd").status_code in {404, 405}
    with pytest.raises(PathSecurityError):
        services.exports.get_file("../escape")
    outside = tmp_path.parent / "outside-export.txt"
    outside.write_text("secret", encoding="utf-8")
    services.exports._files["a" * 32] = outside
    with pytest.raises(PathSecurityError):
        services.exports.get_file("a" * 32)
    with pytest.raises(NotFoundError):
        services.exports.get_job("missing")


def test_export_service_rejects_symlinked_output_root_before_writing(
    isolated_repo: Path,
    tmp_path: Path,
) -> None:
    config = load_project_config(isolated_repo / "project.yaml")
    outside = tmp_path / "outside-native-exports"
    outside.mkdir()
    exports = isolated_repo / "exports"
    exports.mkdir()
    (exports / "strictdoc").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathSecurityError, match="contains a symlink"):
        StrictDocExportService(StrictDocAdapter(config))

    assert list(outside.iterdir()) == []


def test_root_placeholder(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["api"] == "/api/docs"


def test_export_exit_zero_with_only_cache_is_failed(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    def cache_only(
        _requirements_dir: Path,
        output_dir: Path,
        **_kwargs: Any,
    ) -> NativeCommandResult:
        cache = output_dir / "_cache"
        cache.mkdir(parents=True)
        (cache / "stale.json").write_text("{}", encoding="utf-8")
        return NativeCommandResult(
            command=["strictdoc"], returncode=0, stdout="", stderr="", duration_ms=1
        )

    monkeypatch.setattr(services.strictdoc, "run_native_export", cache_only)
    job = services.exports.run("json")

    assert job.status == "failed"
    assert job.created_files == []
    assert job.error is not None and "no final .json artifact" in job.error


def test_export_process_start_error_finishes_as_failed_job(
    services: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_runner(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError("strictdoc executable missing")

    monkeypatch.setattr(services.strictdoc, "runner", missing_runner)
    job = services.exports.run("json")

    assert job.status == "failed"
    assert job.returncode == 127
    assert job.command
    assert job.error is not None and "could not be started" in job.error


def test_export_detects_source_change_during_native_command(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = services.config.managed_document("02_system.sdoc")

    def export_then_edit(
        _requirements_dir: Path,
        output_dir: Path,
        **_kwargs: Any,
    ) -> NativeCommandResult:
        final = output_dir / "json" / "index.json"
        final.parent.mkdir(parents=True)
        final.write_text("{}", encoding="utf-8")
        content = source.read_text(encoding="utf-8")
        source.write_text(content.replace("VERSION: 1.0", "VERSION: 1.1", 1), encoding="utf-8")
        return NativeCommandResult(
            command=["strictdoc"], returncode=0, stdout="", stderr="", duration_ms=1
        )

    monkeypatch.setattr(services.strictdoc, "run_native_export", export_then_edit)
    job = services.exports.run("json")

    assert job.status == "failed"
    assert job.error is not None and "changed during native export" in job.error


def test_pdf_export_requires_explicit_driver_without_running_strictdoc(
    services: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REQPILOT_CHROMEDRIVER", raising=False)

    def must_not_run(*_args: Any, **_kwargs: Any) -> NativeCommandResult:
        raise AssertionError("StrictDoc must not run without an explicit driver")

    monkeypatch.setattr(services.strictdoc, "run_native_export", must_not_run)
    job = services.exports.run("pdf")

    assert job.status == "failed"
    assert job.error is not None and "automatic driver download is disabled" in job.error


def test_pdf_export_passes_validated_driver_to_native_command(
    services: Services,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver = tmp_path / "chromedriver"
    driver.write_text("driver", encoding="utf-8")
    driver.chmod(0o700)
    monkeypatch.setenv("REQPILOT_CHROMEDRIVER", str(driver))
    captured: dict[str, Any] = {}

    def create_pdf(
        _requirements_dir: Path,
        output_dir: Path,
        **kwargs: Any,
    ) -> NativeCommandResult:
        captured.update(kwargs)
        final = output_dir / "pdf" / "bundle.pdf"
        final.parent.mkdir(parents=True)
        final.write_bytes(b"%PDF-1.4\n")
        return NativeCommandResult(
            command=["strictdoc"], returncode=0, stdout="", stderr="", duration_ms=1
        )

    monkeypatch.setattr(services.strictdoc, "run_native_export", create_pdf)
    job = services.exports.run("pdf")

    assert job.status == "succeeded"
    extra_args = captured["extra_args"]
    assert extra_args[-2:] == ("--chromedriver", str(driver.resolve()))


def test_frontend_dist_symlink_is_not_served(
    isolated_repo: Path,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-frontend"
    outside.mkdir()
    (outside / "index.html").write_text("TOP SECRET", encoding="utf-8")
    frontend = isolated_repo / "frontend"
    frontend.mkdir()
    (frontend / "dist").symlink_to(outside, target_is_directory=True)
    config = load_project_config(isolated_repo / "project.yaml")

    with TestClient(create_app(config=config)) as app_client:
        root = app_client.get("/")
        missing = app_client.get("/index.html")

    assert root.status_code == 200
    assert root.json()["api"] == "/api/docs"
    assert missing.status_code == 404
    assert "TOP SECRET" not in missing.text
