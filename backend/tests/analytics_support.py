"""Shared builders for isolated architecture and analytics tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.trace_links import TraceLinkRepository
from reqpilot.config import ProjectConfig, load_project_config
from reqpilot.models import Relation, Requirement


def requirement(
    uid: str,
    type_: str,
    *,
    relations: list[Relation] | None = None,
) -> Requirement:
    """Build a compact normalized StrictDoc requirement for analytics tests."""

    return Requirement(
        uid=uid,
        mid=f"mid_req_{uid.lower().replace('-', '_')}",
        document="requirements/test.sdoc",
        document_title="Test requirements",
        node_type="REQUIREMENT",
        type=type_,
        status="Approved",
        priority="High",
        verification_method="Test",
        owner="pytest",
        title=f"Title {uid}",
        statement=f"Statement {uid}",
        acceptance_criteria=f"Acceptance {uid}",
        relations=relations or [],
        revision="test-revision",
    )


def demo_requirements() -> list[Requirement]:
    """Return requirements covering all ten checked-in trace links and tests."""

    values = [
        requirement("STK-001", "Stakeholder"),
        requirement("STK-002", "Stakeholder"),
        requirement("STK-003", "Stakeholder"),
        requirement("SYS-001", "System"),
        requirement("SYS-002", "System"),
        requirement("SYS-003", "System"),
        requirement("SYS-004", "System"),
        requirement("IF-001", "Interface"),
        requirement("SW-003", "Software"),
        requirement("SAF-001", "Safety"),
        requirement("SAF-002", "Safety"),
    ]
    for number, target in enumerate(
        ["SYS-001", "SYS-002", "SYS-003", "SYS-004", "SAF-001", "SAF-002"],
        start=1,
    ):
        values.append(
            requirement(
                f"TST-{number:03d}",
                "TestCase",
                relations=[Relation(value=target, role="Verifies")],
            )
        )
    return values


def isolated_analytics_config(tmp_path: Path, source_repo: Path) -> ProjectConfig:
    """Create an explicit fixture-mode project without copying canonical requirements."""

    (tmp_path / "fixtures").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        source_repo / "fixtures" / "architecture-fixture.json",
        tmp_path / "fixtures" / "architecture-fixture.json",
    )
    shutil.copy2(source_repo / "trace-links.yaml", tmp_path / "trace-links.yaml")
    shutil.copy2(source_repo / "deleted-uids.json", tmp_path / "deleted-uids.json")
    base = load_project_config(source_repo / "project.yaml")
    return base.model_copy(
        update={
            "repo_root": tmp_path,
            "capella": base.capella.model_copy(update={"mode": "fixture"}),
            "fixture": base.fixture.model_copy(update={"enabled": True}),
        }
    )


def analytics_stack(
    tmp_path: Path, source_repo: Path
) -> tuple[ProjectConfig, list[Requirement], CapellaAdapter, TraceLinkRepository]:
    """Build an isolated, loaded fixture adapter and trace repository."""

    config = isolated_analytics_config(tmp_path, source_repo)
    requirements = demo_requirements()
    capella = CapellaAdapter(config)
    capella.reload()
    links = TraceLinkRepository(config, lambda: requirements, capella)
    return config, requirements, capella, links
