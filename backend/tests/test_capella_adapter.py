"""Capella fixture boundary, live worker command, SVG, and read-only tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from reqpilot.adapters.capella import CapellaAdapter, CapellaAdapterError, sanitize_svg
from reqpilot.analytics_models import FIXTURE_BANNER, CapellaState
from reqpilot.config import ProjectConfig, load_project_config
from reqpilot.errors import PathSecurityError

from tests.analytics_support import isolated_analytics_config


def test_fixture_is_explicit_indexed_and_never_creates_capella_files(
    tmp_path: Path, source_repo: Path
) -> None:
    config = isolated_analytics_config(tmp_path, source_repo)
    adapter = CapellaAdapter(config)
    assert adapter.status().fixture is True
    assert adapter.status().banner == FIXTURE_BANNER
    index = adapter.reload()
    assert index is not None
    assert len(index.elements) == 37
    assert len(index.relations) == 41
    assert len(index.diagrams) == 3
    assert adapter.status().state == CapellaState.FIXTURE
    assert adapter.status().banner == FIXTURE_BANNER
    assert not list(tmp_path.rglob("*.aird"))
    assert not list(tmp_path.rglob("*.capella"))
    assert {item.type for item in index.elements} >= {
        "Actor",
        "OperationalCapability",
        "OperationalActivity",
        "SystemFunction",
        "LogicalComponent",
        "FunctionalExchange",
        "FunctionalChain",
        "Mission",
        "Scenario",
    }


def test_fixture_refuses_implicit_enablement(tmp_path: Path, source_repo: Path) -> None:
    config = isolated_analytics_config(tmp_path, source_repo)
    config = config.model_copy(
        update={"fixture": config.fixture.model_copy(update={"enabled": False})}
    )
    with pytest.raises(CapellaAdapterError, match="fixture.enabled"):
        CapellaAdapter(config).reload()


def test_capella_cache_rejects_state_symlink_without_external_write(
    isolated_repo: Path,
) -> None:
    config = load_project_config(isolated_repo / "project.yaml")
    outside = isolated_repo.with_name(f"{isolated_repo.name}-outside-capella-cache")
    outside.mkdir()
    (isolated_repo / ".reqpilot").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathSecurityError, match="must not contain symlinks"):
        CapellaAdapter(config).reload()

    assert list(outside.iterdir()) == []


def test_filters_uuid_resolution_and_safe_fixture_svg(tmp_path: Path, source_repo: Path) -> None:
    adapter = CapellaAdapter(isolated_analytics_config(tmp_path, source_repo))
    adapter.reload()
    functions = adapter.list_elements(layer="SA", type_="SystemFunction", text="alarm")
    assert "Manage Alarm Lifecycle" in {item.name for item in functions}
    assert all("alarm" in f"{item.name} {item.description}".casefold() for item in functions)
    alarm = adapter.get_element("30000000-0000-4000-8000-000000000312")
    assert alarm.name == "Alarm Manager"
    assert adapter.list_elements(related_to=alarm.uuid)
    svg = adapter.render_diagram("90000000-0000-4000-8000-000000000002")
    assert svg.startswith("<svg")
    assert "FIXTURE" in svg
    assert "<script" not in svg


@pytest.mark.parametrize(
    "svg",
    [
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.test/a"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><rect onclick="x()"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://example.test/x)"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://example.test";</style></svg>',
    ],
)
def test_svg_active_content_is_rejected(svg: str) -> None:
    with pytest.raises(CapellaAdapterError) as caught:
        sanitize_svg(svg)
    assert caught.value.code == "unsafe_svg"


def test_live_worker_is_shell_free_and_model_hashes_do_not_change(
    tmp_path: Path, source_repo: Path
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "pump.aird").write_text("aird", encoding="utf-8")
    (model_dir / "pump.capella").write_text("semantic", encoding="utf-8")
    base = load_project_config(source_repo / "project.yaml")
    config: ProjectConfig = base.model_copy(
        update={
            "repo_root": tmp_path,
            "capella": base.capella.model_copy(
                update={
                    "mode": "live",
                    "model_path": "model",
                    "entrypoint": "pump.aird",
                }
            ),
        }
    )
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        payload = {
            "schema_version": 1,
            "model_id": "pump-station-pilot",
            "source_kind": "live",
            "source_label": "worker",
            "fingerprint": "worker",
            "elements": [],
            "relations": [],
            "diagrams": [],
            "indexed_duration_ms": 0,
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in model_dir.iterdir()
    }
    adapter = CapellaAdapter(config, runner=runner, worker_python="python-capella")
    index = adapter.reload()
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in model_dir.iterdir()
    }
    assert index is not None
    assert adapter.status().state == CapellaState.READY
    assert before == after
    assert calls[0][0][0] == "python-capella"
    assert calls[0][1]["shell"] is False
    assert "--entrypoint" in calls[0][0]


def test_live_model_path_cannot_escape_repository(tmp_path: Path, source_repo: Path) -> None:
    base = load_project_config(source_repo / "project.yaml")
    config = base.model_copy(
        update={
            "repo_root": tmp_path,
            "capella": base.capella.model_copy(
                update={"mode": "live", "model_path": "../outside.aird"}
            ),
        }
    )
    with pytest.raises(PathSecurityError):
        CapellaAdapter(config).reload()


@pytest.mark.skip(reason="REAL CAPELLA TEST: NOT EXECUTED — no legal model is available")
def test_real_capella_model_read_only_contract() -> None:
    """Reserved integration contract; a fixture is never accepted as evidence."""

    raise AssertionError("Only enabled when a real legal Capella model is configured")
