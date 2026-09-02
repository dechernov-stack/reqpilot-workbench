"""Derived dashboard counters and coverage summary."""

from __future__ import annotations

from collections.abc import Callable

from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.git_adapter import GitAdapter
from reqpilot.adapters.trace_links import RequirementProvider, TraceLinkRepository
from reqpilot.analytics_models import CapellaState, DashboardResult
from reqpilot.services.matrices import MatrixService

TextProvider = Callable[[], str | None]


class DashboardService:
    """Aggregate current source-derived metrics without becoming a data store."""

    def __init__(
        self,
        requirement_provider: RequirementProvider,
        capella: CapellaAdapter,
        trace_links: TraceLinkRepository,
        matrices: MatrixService,
        *,
        git: GitAdapter | None = None,
        last_export_provider: TextProvider | None = None,
    ) -> None:
        self.requirement_provider = requirement_provider
        self.capella = capella
        self.trace_links = trace_links
        self.matrices = matrices
        self.git = git
        self.last_export_provider = last_export_provider

    def snapshot(self) -> DashboardResult:
        """Return a deterministic dashboard snapshot from current sources."""

        requirements = list(self.requirement_provider())
        index = self.capella.ensure_loaded()
        capella_status = self.capella.status()
        links = self.trace_links.list_links().items
        test_coverage, uncovered_tests = self.matrices.test_coverage()
        architecture_coverage, uncovered_architecture = self.matrices.architecture_coverage()
        broken = [
            link for link in links if link.status in {"broken_requirement", "broken_architecture"}
        ]
        recent_errors: list[str] = []
        if capella_status.state == CapellaState.ERROR:
            recent_errors.append(capella_status.message)
        validation = self.trace_links.validate()
        recent_errors.extend(
            diagnostic.message
            for diagnostic in validation.diagnostics
            if diagnostic.severity == "error"
        )
        git_status = "unavailable"
        if self.git is not None:
            status = self.git.status()
            if status.available:
                clean = "dirty" if status.dirty else "clean"
                git_status = f"{status.branch or 'detached'} · {clean}"
            elif status.error:
                git_status = f"unavailable · {status.error}"
        return DashboardResult(
            requirements=len(requirements),
            capella_elements=len(index.elements) if index else 0,
            internal_relations=sum(len(item.relations) for item in requirements),
            trace_links=len(links),
            test_coverage=test_coverage,
            architecture_coverage=architecture_coverage,
            broken_links=len(broken),
            capella_status=capella_status,
            fixture_banner=capella_status.banner,
            indexing_duration_ms=capella_status.indexed_duration_ms,
            git_status=git_status,
            last_export=self.last_export_provider() if self.last_export_provider else None,
            uncovered_test_requirements=uncovered_tests,
            uncovered_architecture_requirements=uncovered_architecture,
            recent_errors=sorted(set(recent_errors)),
        )
