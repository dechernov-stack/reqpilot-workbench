"""Focused regression tests for configuration and local serving boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from reqpilot import __main__ as reqpilot_main
from reqpilot.app import _safe_frontend_entry, create_app
from reqpilot.config import ProjectConfig, load_project_config
from reqpilot.errors import ConfigurationError, PathSecurityError, ReqPilotError
from reqpilot.service_container import Services
from ruamel.yaml import YAML


def _project_payload(path: Path) -> dict[str, Any]:
    payload = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_project(path: Path, payload: dict[str, Any]) -> None:
    yaml = YAML()
    with path.open("w", encoding="utf-8") as stream:
        yaml.dump(payload, stream)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_documents", "contains duplicates"),
        ("missing_root", "StrictDoc root does not exist"),
        ("missing_config", "StrictDoc config does not exist"),
        ("managed_non_sdoc", "Managed StrictDoc document is invalid"),
        ("managed_outside_root", "Managed document escapes StrictDoc root"),
        ("document_mid_count", "one unique MID per document"),
        ("document_mid_mapping", "map exactly the managed document allowlist"),
        ("export_at_repo_root", "cannot be the repository root"),
        ("deleted_uids_in_requirements", "cannot overlap requirements sources"),
        ("deleted_uids_in_state", "must be tracked outside .reqpilot"),
        ("deleted_uids_invalid_json", "is not valid JSON"),
        ("deleted_uids_invalid_shape", "has an invalid shape"),
        ("trace_links_wrong_extension", "must be an existing YAML file"),
        ("trace_links_in_requirements", "cannot overlap requirements sources"),
        ("capella_cache_wrong_extension", "must address a JSON file"),
        ("capella_cache_directory", "must not address a directory"),
        ("capella_cache_in_requirements", "cannot overlap requirements sources"),
        ("capella_cache_is_canonical", "overlaps a canonical file"),
        ("fixture_mode_mismatch", "requires capella.mode=fixture"),
        ("fixture_missing", "must be an existing file"),
    ],
)
def test_project_config_rejects_unsafe_or_ambiguous_layouts(
    isolated_repo: Path,
    case: str,
    message: str,
) -> None:
    """Every canonical/generated path must retain an unambiguous safe role."""

    config_path = isolated_repo / "project.yaml"
    payload = _project_payload(config_path)
    strictdoc = payload["strictdoc"]

    if case == "duplicate_documents":
        strictdoc["managed_documents"].append(strictdoc["managed_documents"][0])
    elif case == "missing_root":
        strictdoc["root"] = "missing-requirements"
    elif case == "missing_config":
        strictdoc["config"] = "requirements/missing-config.py"
    elif case == "managed_non_sdoc":
        candidate = isolated_repo / "requirements" / "notes.txt"
        candidate.write_text("not StrictDoc\n", encoding="utf-8")
        strictdoc["managed_documents"][0] = "requirements/notes.txt"
    elif case == "managed_outside_root":
        candidate = isolated_repo / "outside.sdoc"
        candidate.write_text("[DOCUMENT]\n", encoding="utf-8")
        strictdoc["managed_documents"][0] = "outside.sdoc"
    elif case == "document_mid_count":
        strictdoc["document_mids"].pop(next(iter(strictdoc["document_mids"])))
    elif case == "document_mid_mapping":
        mids = strictdoc["document_mids"]
        keys = list(mids)
        mids[keys[0]] = mids[keys[1]]
    elif case == "export_at_repo_root":
        strictdoc["export_root"] = "."
    elif case == "deleted_uids_in_requirements":
        candidate = isolated_repo / "requirements" / "deleted.json"
        candidate.write_text('{"uids": []}\n', encoding="utf-8")
        strictdoc["deleted_uids"] = "requirements/deleted.json"
    elif case == "deleted_uids_in_state":
        candidate = isolated_repo / ".reqpilot" / "deleted.json"
        candidate.parent.mkdir()
        candidate.write_text('{"uids": []}\n', encoding="utf-8")
        strictdoc["deleted_uids"] = ".reqpilot/deleted.json"
    elif case == "deleted_uids_invalid_json":
        (isolated_repo / "deleted-uids.json").write_text("not-json\n", encoding="utf-8")
    elif case == "deleted_uids_invalid_shape":
        (isolated_repo / "deleted-uids.json").write_text('{"deleted": []}\n', encoding="utf-8")
    elif case == "trace_links_wrong_extension":
        candidate = isolated_repo / "trace-links.json"
        candidate.write_text('{"links": []}\n', encoding="utf-8")
        payload["trace_links"]["path"] = "trace-links.json"
    elif case == "trace_links_in_requirements":
        candidate = isolated_repo / "requirements" / "trace-links.yaml"
        candidate.write_text("schema_version: 1\nlinks: []\n", encoding="utf-8")
        payload["trace_links"]["path"] = "requirements/trace-links.yaml"
    elif case == "capella_cache_wrong_extension":
        payload["capella"]["cache_path"] = ".reqpilot/cache/capella-index.txt"
    elif case == "capella_cache_directory":
        (isolated_repo / "cache.json").mkdir()
        payload["capella"]["cache_path"] = "cache.json"
    elif case == "capella_cache_in_requirements":
        candidate = isolated_repo / "requirements" / "cache.json"
        candidate.write_text("{}\n", encoding="utf-8")
        payload["capella"]["cache_path"] = "requirements/cache.json"
    elif case == "capella_cache_is_canonical":
        payload["capella"]["cache_path"] = "deleted-uids.json"
    elif case == "fixture_mode_mismatch":
        payload["capella"]["mode"] = "disabled"
    elif case == "fixture_missing":
        payload["fixture"]["path"] = "fixtures/missing.json"
    else:
        raise AssertionError(f"Unhandled case: {case}")

    _write_project(config_path, payload)
    with pytest.raises(ConfigurationError, match=message):
        load_project_config(config_path)


def test_project_loader_rejects_missing_and_non_mapping_files(tmp_path: Path) -> None:
    """A missing or structurally unrelated YAML file cannot become project config."""

    missing = tmp_path / "missing.yaml"
    with pytest.raises(ConfigurationError, match="does not exist"):
        load_project_config(missing)

    sequence = tmp_path / "sequence.yaml"
    sequence.write_text("- not\n- a\n- project\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="root must be a mapping"):
        load_project_config(sequence)


def test_state_directory_creation_and_escape_rejection(project_config: ProjectConfig) -> None:
    """Derived state is created inside the repository and never through unsafe parts."""

    created = project_config.ensure_state_dir("coverage", "nested")
    assert created.is_dir()
    assert created.relative_to(project_config.repo_root) == Path(".reqpilot/coverage/nested")

    with pytest.raises(PathSecurityError, match="safe relative parts"):
        project_config.ensure_state_dir("..", "escape")
    with pytest.raises(PathSecurityError, match="escapes repository root"):
        project_config.resolve_repo_path("../escape.json")
    with pytest.raises(PathSecurityError, match="escapes repository root"):
        project_config.reject_repo_path_symlinks("../escape.json")

    occupied = project_config.repo_root / ".reqpilot" / "occupied"
    occupied.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(PathSecurityError, match="Cannot create"):
        project_config.ensure_state_dir("occupied")


def test_frontend_static_routes_and_trusted_hosts(
    isolated_repo: Path,
    project_config: ProjectConfig,
    services: Services,
) -> None:
    """Built assets are local-only, while client routes fall back to the SPA entry."""

    frontend_dist = isolated_repo / "frontend" / "dist"
    assets = frontend_dist / "assets"
    assets.mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<h1>ReqPilot UI</h1>\n", encoding="utf-8")
    (frontend_dist / "plain.txt").write_text("local artifact\n", encoding="utf-8")
    (assets / "app.js").write_text("console.log('local');\n", encoding="utf-8")

    outside = isolated_repo.parent / "outside-index.html"
    outside.write_text("outside\n", encoding="utf-8")
    assert _safe_frontend_entry(isolated_repo, outside, directory=False) is None

    with TestClient(create_app(config=project_config, services=services)) as app_client:
        root = app_client.get("/")
        asset = app_client.get("/assets/app.js")
        direct_file = app_client.get("/plain.txt")
        spa_route = app_client.get("/requirements/SYS-002")
        untrusted = app_client.get("/api/health", headers={"host": "attacker.example"})

    assert root.status_code == 200
    assert "ReqPilot UI" in root.text
    assert asset.status_code == 200
    assert "console.log" in asset.text
    assert direct_file.text == "local artifact\n"
    assert "ReqPilot UI" in spa_route.text
    assert untrusted.status_code == 400
    assert "Invalid host header" in untrusted.text


def test_error_details_and_module_entrypoint(
    project_config: ProjectConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnostics remain structured and the module entrypoint binds to loopback."""

    error = ReqPilotError(
        "native_failure",
        "StrictDoc failed",
        422,
        diagnostics=[{"code": "strictdoc", "message": "invalid document"}],
    )
    assert error.as_detail()["diagnostics"][0]["code"] == "strictdoc"

    call: dict[str, Any] = {}
    monkeypatch.setattr(reqpilot_main, "load_project_config", lambda _path: project_config)

    def fake_run(application: str, **kwargs: Any) -> None:
        call["application"] = application
        call.update(kwargs)

    monkeypatch.setattr(reqpilot_main.uvicorn, "run", fake_run)
    reqpilot_main.main()

    assert call == {
        "application": "reqpilot.app:app",
        "host": "127.0.0.1",
        "port": 8080,
        "reload": False,
    }
