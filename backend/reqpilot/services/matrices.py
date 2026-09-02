"""Sparse, deterministic traceability matrices and coverage calculations."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Sequence

from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.trace_links import RequirementProvider, TraceLinkRepository
from reqpilot.analytics_models import (
    CapellaElement,
    Coverage,
    MatrixAxisItem,
    MatrixCell,
    MatrixResult,
)
from reqpilot.models import Requirement

ARCHITECTURE_COVERAGE_TYPES = {"System", "Software", "Interface", "Safety"}
TEST_COVERAGE_TYPES = {"System", "Safety"}


def coverage(numerator: int, denominator: int) -> Coverage:
    """Build a coverage value without division-by-zero ambiguity."""

    percent = round((numerator / denominator * 100) if denominator else 100.0, 2)
    return Coverage(numerator=numerator, denominator=denominator, percent=percent)


def is_function(element: CapellaElement) -> bool:
    """Return whether an architecture element is a function-like matrix column."""

    return element.type.endswith("Function") or element.type == "OperationalActivity"


def is_component(element: CapellaElement) -> bool:
    """Return whether an architecture element is a component-like matrix column."""

    return element.type.endswith("Component") or element.type == "System"


class MatrixService:
    """Build the four required matrices from canonical-source-derived indexes."""

    def __init__(
        self,
        requirement_provider: RequirementProvider,
        capella: CapellaAdapter,
        trace_links: TraceLinkRepository,
    ) -> None:
        self.requirement_provider = requirement_provider
        self.capella = capella
        self.trace_links = trace_links

    def requirements_tests(self, *, text: str | None = None) -> MatrixResult:
        """Return requirements ↔ TestCase verification coverage."""

        requirements = self._requirements()
        rows_req = [item for item in requirements if item.type != "TestCase"]
        tests = [item for item in requirements if item.type == "TestCase"]
        rows = self._requirement_axis(rows_req, text=text)
        columns = self._requirement_axis(tests, text=text)
        row_ids = {item.id for item in rows}
        column_ids = {item.id for item in columns}
        cell_relations: dict[tuple[str, str], set[str]] = defaultdict(set)
        requirements_by_uid = {item.uid: item for item in requirements}
        for item in requirements:
            for relation in item.relations:
                relation_name = relation.role or relation.type
                target = requirements_by_uid.get(relation.value)
                if target is None or relation_name != "Verifies":
                    continue
                if item.type == "TestCase" and target.type != "TestCase":
                    row_id, column_id = target.uid, item.uid
                elif target.type == "TestCase" and item.type != "TestCase":
                    row_id, column_id = item.uid, target.uid
                else:
                    continue
                if row_id in row_ids and column_id in column_ids:
                    cell_relations[(row_id, column_id)].add("Verifies")
        cells = self._cells(cell_relations)
        eligible = [item for item in rows_req if item.type in TEST_COVERAGE_TYPES]
        covered = {cell.row_id for cell in cells if cell.row_id in {item.uid for item in eligible}}
        return MatrixResult(
            id="requirements-tests",
            title="Требования ↔ тесты",
            rows=rows,
            columns=columns,
            cells=cells,
            coverage=coverage(len(covered), len(eligible)),
        )

    def requirements_functions(self, *, text: str | None = None) -> MatrixResult:
        """Return requirements ↔ architecture functions trace links."""

        return self._requirements_architecture(
            matrix_id="requirements-functions",
            title="Требования ↔ функции",
            predicate=is_function,
            text=text,
        )

    def requirements_components(self, *, text: str | None = None) -> MatrixResult:
        """Return requirements ↔ architecture components trace links."""

        return self._requirements_architecture(
            matrix_id="requirements-components",
            title="Требования ↔ компоненты",
            predicate=is_component,
            text=text,
        )

    def functions_components(self, *, text: str | None = None) -> MatrixResult:
        """Return function ↔ component allocations from the architecture index."""

        index = self.capella.ensure_loaded()
        if index is None:
            return MatrixResult(
                id="functions-components",
                title="Функции ↔ компоненты",
                rows=[],
                columns=[],
                cells=[],
                coverage=coverage(0, 0),
            )
        by_uuid = {element.uuid: element for element in index.elements}
        functions = [element for element in index.elements if is_function(element)]
        components = [element for element in index.elements if is_component(element)]
        rows = self._architecture_axis(functions, text=text)
        columns = self._architecture_axis(components, text=text)
        row_ids = {item.id for item in rows}
        column_ids = {item.id for item in columns}
        values: dict[tuple[str, str], set[str]] = defaultdict(set)
        for relation in index.relations:
            if "allocat" not in relation.type.casefold():
                continue
            source = by_uuid.get(relation.source_uuid)
            target = by_uuid.get(relation.target_uuid)
            if source is None or target is None:
                continue
            if is_function(source) and is_component(target):
                row_id, column_id = source.uuid, target.uuid
            elif is_function(target) and is_component(source):
                row_id, column_id = target.uuid, source.uuid
            else:
                continue
            if row_id in row_ids and column_id in column_ids:
                values[(row_id, column_id)].add(relation.type)
        cells = self._cells(values)
        covered = {cell.row_id for cell in cells}
        return MatrixResult(
            id="functions-components",
            title="Функции ↔ компоненты",
            rows=rows,
            columns=columns,
            cells=cells,
            coverage=coverage(len(covered), len(rows)),
        )

    def architecture_coverage(self) -> tuple[Coverage, list[str]]:
        """Return task-defined architecture coverage and uncovered UIDs."""

        requirements = [
            item for item in self._requirements() if item.type in ARCHITECTURE_COVERAGE_TYPES
        ]
        valid_uids = {
            link.requirement.uid
            for link in self.trace_links.list_links().items
            if link.status == "valid"
        }
        uncovered = sorted(item.uid for item in requirements if item.uid not in valid_uids)
        return coverage(len(requirements) - len(uncovered), len(requirements)), uncovered

    def test_coverage(self) -> tuple[Coverage, list[str]]:
        """Return incoming-TestCase-Verifies coverage for System/Safety requirements."""

        matrix = self.requirements_tests()
        covered = {cell.row_id for cell in matrix.cells}
        eligible = [item for item in self._requirements() if item.type in TEST_COVERAGE_TYPES]
        uncovered = sorted(item.uid for item in eligible if item.uid not in covered)
        return matrix.coverage, uncovered

    @staticmethod
    def to_csv(matrix: MatrixResult) -> str:
        """Serialize the current filtered matrix to UTF-8 CSV text."""

        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([matrix.title, *[f"{item.id} · {item.label}" for item in matrix.columns]])
        cells = {(cell.row_id, cell.column_id): cell for cell in matrix.cells}
        for row in matrix.rows:
            values = [f"{row.id} · {row.label}"]
            for column in matrix.columns:
                cell = cells.get((row.id, column.id))
                values.append("; ".join(cell.relations) if cell else "")
            writer.writerow(values)
        return stream.getvalue()

    def _requirements_architecture(
        self,
        *,
        matrix_id: str,
        title: str,
        predicate: Callable[[CapellaElement], bool],
        text: str | None,
    ) -> MatrixResult:
        requirements = [item for item in self._requirements() if item.type != "TestCase"]
        index = self.capella.ensure_loaded()
        elements = index.elements if index else []
        selected = [element for element in elements if predicate(element)]
        rows = self._requirement_axis(requirements, text=text)
        columns = self._architecture_axis(selected, text=text)
        row_ids = {item.id for item in rows}
        column_ids = {item.id for item in columns}
        values: dict[tuple[str, str], set[str]] = defaultdict(set)
        link_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
        for link in self.trace_links.list_links().items:
            key = (link.requirement.uid, link.architecture.uuid)
            if link.status != "valid" or key[0] not in row_ids or key[1] not in column_ids:
                continue
            values[key].add(link.relation)
            link_ids[key].add(link.id)
        cells = self._cells(values, link_ids)
        eligible = [
            requirement
            for requirement in requirements
            if requirement.type in ARCHITECTURE_COVERAGE_TYPES and requirement.uid in row_ids
        ]
        covered = {cell.row_id for cell in cells}
        return MatrixResult(
            id=matrix_id,
            title=title,
            rows=rows,
            columns=columns,
            cells=cells,
            coverage=coverage(len(covered & {item.uid for item in eligible}), len(eligible)),
        )

    def _requirements(self) -> list[Requirement]:
        return sorted(self.requirement_provider(), key=lambda item: item.uid)

    @staticmethod
    def _requirement_axis(
        requirements: Sequence[Requirement], *, text: str | None
    ) -> list[MatrixAxisItem]:
        needle = text.casefold().strip() if text else None
        values = [
            MatrixAxisItem(
                id=requirement.uid,
                label=requirement.title or requirement.uid,
                type=requirement.type or "Requirement",
            )
            for requirement in requirements
            if not needle
            or needle
            in f"{requirement.uid} {requirement.title or ''} {requirement.type or ''}".casefold()
        ]
        return sorted(values, key=lambda item: (item.type, item.id, item.label))

    @staticmethod
    def _architecture_axis(
        elements: Sequence[CapellaElement], *, text: str | None
    ) -> list[MatrixAxisItem]:
        needle = text.casefold().strip() if text else None
        values = [
            MatrixAxisItem(id=element.uuid, label=element.name, type=element.type)
            for element in elements
            if not needle or needle in f"{element.uuid} {element.name} {element.type}".casefold()
        ]
        return sorted(values, key=lambda item: (item.type, item.label, item.id))

    @staticmethod
    def _cells(
        values: dict[tuple[str, str], set[str]],
        link_ids: dict[tuple[str, str], set[str]] | None = None,
    ) -> list[MatrixCell]:
        identifiers = link_ids or {}
        return [
            MatrixCell(
                row_id=row_id,
                column_id=column_id,
                relations=sorted(relations),
                link_ids=sorted(identifiers.get((row_id, column_id), set())),
            )
            for (row_id, column_id), relations in sorted(values.items())
        ]
