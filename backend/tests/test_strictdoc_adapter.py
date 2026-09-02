"""Unit and native integration tests for the StrictDoc JSON adapter."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from reqpilot.config import ProjectConfig, load_project_config
from reqpilot.errors import (
    ConfigurationError,
    NotFoundError,
    PathSecurityError,
    StrictDocCommandError,
)
from reqpilot.models import NativeCommandResult
from reqpilot.service_container import build_services
from reqpilot.strictdoc_adapter import PINNED_STRICTDOC_VERSION, StrictDocAdapter
from ruamel.yaml import YAML


def test_config_paths_and_allowlist(project_config: ProjectConfig) -> None:
    assert project_config.server.host == "127.0.0.1"
    assert project_config.requirements_dir.name == "requirements"
    assert len(project_config.managed_document_paths) == 5
    assert project_config.managed_document("02_system.sdoc").name == "02_system.sdoc"
    assert project_config.managed_document("requirements/02_system.sdoc").name == "02_system.sdoc"
    with pytest.raises(Exception, match="not managed"):
        project_config.managed_document("../../etc/passwd")


def test_invalid_configuration_is_rejected(isolated_repo: Path) -> None:
    path = isolated_repo / "invalid-project.yaml"
    source = (isolated_repo / "project.yaml").read_text(encoding="utf-8")
    path.write_text(source.replace("host: 127.0.0.1", "host: 0.0.0.0"), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid project configuration"):
        load_project_config(path)


def test_malformed_yaml_configuration_is_rejected(isolated_repo: Path) -> None:
    path = isolated_repo / "malformed-project.yaml"
    path.write_text("project: [unterminated\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Invalid project configuration"):
        load_project_config(path)


def test_native_refresh_filters_and_revision(project_config: ProjectConfig) -> None:
    adapter = StrictDocAdapter(project_config)
    listing = adapter.refresh()
    assert adapter.version == PINNED_STRICTDOC_VERSION
    assert listing.total == 24
    assert len(listing.revision) == 64
    assert len({item.uid for item in listing.items}) == 24
    assert len({item.mid for item in listing.items}) == 24
    assert adapter.list_requirements(text="гистерезис").total == 1
    assert adapter.list_requirements(status="Approved").total > 0
    assert adapter.list_requirements(type_="Safety").total == 2
    assert adapter.list_requirements(document="02_system.sdoc").total == 6
    system = adapter.get_requirement("SYS-002")
    assert system.document == "requirements/02_system.sdoc"
    assert system.type == "System"
    assert system.relations[0].value == "STK-002"
    assert "давление" in system.tags
    with pytest.raises(NotFoundError):
        adapter.get_requirement("UNKNOWN-404")
    assert adapter.last_command is not None
    assert adapter.last_command.command[0]
    assert adapter.last_refresh_epoch is not None
    assert adapter.cache_path.is_file()


def test_native_subprocess_is_an_argument_list_without_shell(
    project_config: ProjectConfig, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def fake_runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    adapter = StrictDocAdapter(project_config, runner=fake_runner)
    result = adapter.run_native_export(
        project_config.requirements_dir,
        tmp_path / "out",
        export_format="json",
    )
    assert result.returncode == 0
    assert captured["shell"] is False
    assert isinstance(captured["command"], list)
    assert "--formats=json" in captured["command"]
    assert captured["env"]["PATH"].split(os.pathsep)[0] == str(
        Path(adapter.python_executable).absolute().parent
    )


def test_timeout_and_diagnostic_normalization(
    project_config: ProjectConfig, tmp_path: Path
) -> None:
    def timeout_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=0.01, output="before", stderr="blocked")

    adapter = StrictDocAdapter(project_config, runner=timeout_runner, timeout_seconds=0.01)
    result = adapter.run_native_export(
        project_config.requirements_dir,
        tmp_path / "out",
        export_format="json",
    )
    assert result.returncode == 124
    diagnostic = adapter.command_diagnostics(result)[0]
    assert diagnostic.code == "nonzero_exit"
    assert diagnostic.severity == "error"


def test_process_start_error_is_a_structured_native_failure(
    project_config: ProjectConfig,
    tmp_path: Path,
) -> None:
    def missing_runner(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("strictdoc executable missing")

    adapter = StrictDocAdapter(project_config, runner=missing_runner)
    result = adapter.run_native_export(
        project_config.requirements_dir,
        tmp_path / "out",
        export_format="json",
    )

    assert result.returncode == 127
    assert "could not be started" in result.stderr
    assert adapter.command_diagnostics(result)[0].code == "nonzero_exit"


def test_payload_shape_and_duplicate_ids_are_rejected(project_config: ProjectConfig) -> None:
    adapter = StrictDocAdapter(project_config)
    with pytest.raises(StrictDocCommandError, match="DOCUMENTS"):
        adapter.normalize_payload({}, revision="x" * 64)
    with pytest.raises(StrictDocCommandError, match="document count"):
        adapter.normalize_payload({"DOCUMENTS": []}, revision="x" * 64)

    documents: list[dict[str, Any]] = [
        {"MID": mid, "TITLE": path.name, "NODES": []}
        for mid, path in project_config.managed_documents_by_mid.items()
    ]
    duplicate = {
        "_NODE_TYPE": "REQUIREMENT",
        "MID": "same-mid",
        "UID": "SAME-001",
        "TYPE": "System",
        "STATUS": "Draft",
        "PRIORITY": "Low",
        "VERIFICATION_METHOD": "Test",
        "OWNER": "Test",
        "TITLE": "Test",
        "STATEMENT": "Test",
        "ACCEPTANCE_CRITERIA": "Test",
    }
    documents[0]["NODES"] = [duplicate, duplicate]
    with pytest.raises(StrictDocCommandError, match="Duplicate"):
        adapter.normalize_payload({"DOCUMENTS": documents}, revision="x" * 64)


def test_command_diagnostic_success(project_config: ProjectConfig) -> None:
    adapter = StrictDocAdapter(project_config)
    result = NativeCommandResult(
        command=["python", "strictdoc"],
        returncode=0,
        stdout="ok",
        stderr="",
        duration_ms=10,
    )
    diagnostic = adapter.command_diagnostics(result)[0]
    assert diagnostic.code == "native_export_ok"
    assert diagnostic.severity == "info"


def test_validate_native_project(project_config: ProjectConfig) -> None:
    result = StrictDocAdapter(project_config).validate()
    assert result.valid is True
    assert result.diagnostics[0].code == "native_export_ok"


def test_native_documents_map_by_mid_when_allowlist_is_reversed(isolated_repo: Path) -> None:
    yaml = YAML()
    config_path = isolated_repo / "project.yaml"
    raw = yaml.load(config_path.read_text(encoding="utf-8"))
    raw["strictdoc"]["managed_documents"] = list(reversed(raw["strictdoc"]["managed_documents"]))
    with config_path.open("w", encoding="utf-8") as stream:
        yaml.dump(raw, stream)

    adapter = StrictDocAdapter(load_project_config(config_path))
    listing = adapter.refresh()

    by_uid = {item.uid: item for item in listing.items}
    assert by_uid["STK-001"].document_path == "requirements/01_stakeholder.sdoc"
    assert by_uid["STK-001"].document == by_uid["STK-001"].document_path
    assert by_uid["TST-001"].document_path == "requirements/05_tests.sdoc"
    assert by_uid["STK-001"].section_path == []


def test_state_symlink_is_rejected_without_writing_outside(isolated_repo: Path) -> None:
    config = load_project_config(isolated_repo / "project.yaml")
    outside = isolated_repo.with_name(f"{isolated_repo.name}-outside-state")
    outside.mkdir()
    (isolated_repo / ".reqpilot").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathSecurityError, match="must not contain symlinks"):
        build_services(config)

    assert list(outside.iterdir()) == []


def test_export_root_inside_requirements_is_rejected(isolated_repo: Path) -> None:
    yaml = YAML()
    config_path = isolated_repo / "project.yaml"
    raw = yaml.load(config_path.read_text(encoding="utf-8"))
    raw["strictdoc"]["export_root"] = "requirements/generated"
    with config_path.open("w", encoding="utf-8") as stream:
        yaml.dump(raw, stream)

    with pytest.raises(ConfigurationError, match="inside the requirements root"):
        load_project_config(config_path)


def test_deleted_uid_registry_is_required_and_valid(isolated_repo: Path) -> None:
    registry = isolated_repo / "deleted-uids.json"
    registry.unlink()
    with pytest.raises(ConfigurationError, match="must be a JSON file"):
        load_project_config(isolated_repo / "project.yaml")

    registry.write_text('{"uids": ["OLD-001", "OLD-001"]}\n', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="invalid UIDs"):
        load_project_config(isolated_repo / "project.yaml")


def test_strictdoc_config_must_be_inside_requirements_root(isolated_repo: Path) -> None:
    yaml = YAML()
    config_path = isolated_repo / "project.yaml"
    raw = yaml.load(config_path.read_text(encoding="utf-8"))
    shutil_path = isolated_repo / "outside_strictdoc_config.py"
    shutil_path.write_text("project_config = {}\n", encoding="utf-8")
    raw["strictdoc"]["config"] = shutil_path.name
    with config_path.open("w", encoding="utf-8") as stream:
        yaml.dump(raw, stream)

    with pytest.raises(ConfigurationError, match="inside the requirements root"):
        load_project_config(config_path)


def test_refresh_retries_if_sources_change_during_native_read(
    project_config: ProjectConfig,
) -> None:
    source = project_config.managed_document("02_system.sdoc")
    original = source.read_text(encoding="utf-8")
    changed = original.replace(
        "TITLE: Обновление состояния не позднее 2 секунд",
        "TITLE: Обновление состояния не позднее 2 секунд — внешний редактор",
        1,
    )
    calls = 0
    native_runner = subprocess.run

    def editing_runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        completed = native_runner(command, **kwargs)
        if calls == 1:
            source.write_text(changed, encoding="utf-8")
        return completed

    adapter = StrictDocAdapter(project_config, runner=editing_runner)
    listing = adapter.refresh()

    assert calls == 2
    assert listing.revision == adapter.calculate_revision()
    assert adapter.get_requirement("SYS-001").title is not None
    assert adapter.get_requirement("SYS-001").title.endswith("внешний редактор")


def test_requirements_tree_symlink_is_rejected_before_native_read(
    project_config: ProjectConfig,
) -> None:
    outside = project_config.repo_root.with_name(
        f"{project_config.repo_root.name}-external-style.css"
    )
    outside.write_text("secret external content", encoding="utf-8")
    (project_config.requirements_dir / "external.css").symlink_to(outside)
    calls = 0

    def must_not_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise AssertionError("Native StrictDoc must not read a symlinked source tree")

    adapter = StrictDocAdapter(project_config, runner=must_not_run)
    with pytest.raises(PathSecurityError, match="contains a symlink"):
        adapter.refresh()

    assert calls == 0
    assert outside.read_text(encoding="utf-8") == "secret external content"


def test_project_config_and_trace_repository_symlinks_are_rejected(
    isolated_repo: Path,
) -> None:
    alias = isolated_repo / "project-alias.yaml"
    alias.symlink_to(isolated_repo / "project.yaml")
    with pytest.raises(ConfigurationError, match="must not be a symlink"):
        load_project_config(alias)

    trace_path = isolated_repo / "trace-links.yaml"
    trace_path.unlink()
    trace_path.symlink_to(isolated_repo / "requirements" / "01_stakeholder.sdoc")
    with pytest.raises(PathSecurityError, match="must not contain symlinks"):
        load_project_config(isolated_repo / "project.yaml")
