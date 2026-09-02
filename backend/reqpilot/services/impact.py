"""Cycle-safe impact analysis over the unified graph."""

from __future__ import annotations

from collections import defaultdict

from reqpilot.adapters.trace_links import TraceLinkRepository
from reqpilot.analytics_models import GraphEdge, GraphNode, ImpactGroup, ImpactResult
from reqpilot.errors import NotFoundError
from reqpilot.services.graph import GraphService, capella_node_id, requirement_node_id

GROUP_LABELS = {
    "parents": "Родительские требования",
    "children": "Дочерние требования",
    "dependencies": "Зависимые требования",
    "requirements": "Связанные требования",
    "tests": "Тесты",
    "functions": "Функции",
    "components": "Компоненты",
    "exchanges": "Обмены",
    "chains": "Функциональные цепочки",
    "allocations": "Allocations",
    "diagrams": "Диаграммы",
    "architecture": "Архитектурные соседи",
    "broken": "Битые или недоступные UUID",
}


class ImpactService:
    """Produce grouped nodes and concrete shortest paths for one focus object."""

    def __init__(self, graph: GraphService, trace_links: TraceLinkRepository) -> None:
        self.graph = graph
        self.trace_links = trace_links

    def for_requirement(self, uid: str, *, depth: int = 3) -> ImpactResult:
        """Analyze requirement parents, tests, architecture, diagrams, and broken links."""

        return self._analyze(requirement_node_id(uid), depth=depth, focus_kind="requirement")

    def for_capella(self, uuid: str, *, depth: int = 3) -> ImpactResult:
        """Analyze Capella neighbours, allocations, requirements, diagrams, and tests."""

        return self._analyze(capella_node_id(uuid), depth=depth, focus_kind="capella")

    def _analyze(self, focus_id: str, *, depth: int, focus_kind: str) -> ImpactResult:
        if not 1 <= depth <= 4:
            raise ValueError("Impact depth must be between 1 and 4.")
        graph = self.graph.build(focus=focus_id, depth=depth, max_nodes=10_000)
        node_map = {node.id: node for node in graph.nodes}
        focus = node_map.get(focus_id)
        if focus is None:
            kind = "Requirement" if focus_kind == "requirement" else "Capella element"
            identifier = focus_id.split(":", 1)[-1]
            raise NotFoundError(kind, identifier)
        incident = self._incident(graph.edges)
        grouped: dict[str, list[GraphNode]] = defaultdict(list)
        for node in graph.nodes:
            if node.id == focus_id:
                continue
            key = self._group(node, focus_id, incident, focus_kind)
            grouped[key].append(node)
        groups = [
            ImpactGroup(
                key=key,
                label=GROUP_LABELS[key],
                nodes=sorted(values, key=lambda node: (node.type, node.label, node.id)),
            )
            for key, values in sorted(grouped.items(), key=lambda item: item[0])
        ]
        paths = []
        for node in sorted(graph.nodes, key=lambda item: item.id):
            if node.id == focus_id:
                continue
            path = self.graph.shortest_path(focus_id, node.id, graph.edges)
            if path is not None and path.length <= depth:
                paths.append(path)
        broken_links = self._broken_links(focus_id, focus_kind)
        return ImpactResult(
            focus=focus,
            depth=depth,
            groups=groups,
            paths=paths,
            broken_links=broken_links,
        )

    @staticmethod
    def _incident(edges: list[GraphEdge]) -> dict[str, list[GraphEdge]]:
        result: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in edges:
            result[edge.source].append(edge)
            result[edge.target].append(edge)
        return result

    @staticmethod
    def _group(
        node: GraphNode,
        focus_id: str,
        incident: dict[str, list[GraphEdge]],
        focus_kind: str,
    ) -> str:
        if node.broken or node.source == "placeholder":
            return "broken"
        if node.type == "Diagram":
            return "diagrams"
        if node.type == "TestCase":
            return "tests"
        if focus_kind == "requirement" and node.source == "strictdoc":
            direct = [
                edge
                for edge in incident.get(focus_id, [])
                if node.id in {edge.source, edge.target} and edge.origin == "strictdoc"
            ]
            if any("Depend" in edge.relation or edge.relation == "RequiredBy" for edge in direct):
                return "dependencies"
            if any(edge.source == focus_id for edge in direct):
                return "parents"
            if any(edge.target == focus_id for edge in direct):
                return "children"
            return "requirements"
        if node.source == "strictdoc":
            return "requirements"
        if node.type.endswith("Function") or node.type == "OperationalActivity":
            return "functions"
        if node.type.endswith("Component") or node.type == "System":
            allocation_edges = [
                edge for edge in incident.get(node.id, []) if "allocat" in edge.relation.casefold()
            ]
            return "allocations" if focus_kind == "capella" and allocation_edges else "components"
        if "Exchange" in node.type:
            return "exchanges"
        if "Chain" in node.type:
            return "chains"
        return "architecture"

    def _broken_links(self, focus_id: str, focus_kind: str) -> list[str]:
        identifiers: list[str] = []
        for link in self.trace_links.list_links().items:
            if link.status not in {"broken_architecture", "architecture_unavailable"}:
                continue
            if (
                focus_kind == "requirement"
                and focus_id == requirement_node_id(link.requirement.uid)
            ) or (focus_kind == "capella" and focus_id == capella_node_id(link.architecture.uuid)):
                identifiers.append(link.id)
        return sorted(identifiers)
