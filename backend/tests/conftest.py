"""Shared isolated-project fixtures for backend tests."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reqpilot.app import create_app
from reqpilot.config import ProjectConfig, load_project_config
from reqpilot.service_container import Services, build_services


@pytest.fixture
def source_repo() -> Path:
    """Return the repository root containing the checked-in demo project."""

    return Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_repo(tmp_path: Path, source_repo: Path) -> Path:
    """Copy only canonical configuration and requirements for mutation tests."""

    shutil.copytree(
        source_repo / "requirements",
        tmp_path / "requirements",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(source_repo / "fixtures", tmp_path / "fixtures")
    shutil.copy2(source_repo / "trace-links.yaml", tmp_path / "trace-links.yaml")
    shutil.copy2(source_repo / "deleted-uids.json", tmp_path / "deleted-uids.json")
    shutil.copy2(source_repo / "project.yaml", tmp_path / "project.yaml")
    return tmp_path


@pytest.fixture
def project_config(isolated_repo: Path) -> ProjectConfig:
    """Load the isolated project configuration."""

    return load_project_config(isolated_repo / "project.yaml")


@pytest.fixture
def services(project_config: ProjectConfig) -> Services:
    """Build services whose canonical writes are confined to pytest tmp_path."""

    return build_services(project_config)


@pytest.fixture
def client(project_config: ProjectConfig, services: Services) -> Iterator[TestClient]:
    """Yield a TestClient bound to the isolated service container."""

    with TestClient(create_app(config=project_config, services=services)) as test_client:
        yield test_client
