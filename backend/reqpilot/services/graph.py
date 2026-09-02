"""Deterministic unified StrictDoc/Capella/trace-link graph service."""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence

from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.trace_links import RequirementProvider, TraceLinkRepository
from reqpilot.analytics_models import GraphEdge, GraphNode, GraphPath, GraphResult
from reqpilot.errors import NotFoundError
from reqpilot.models import Requirement


def requirement_node_id(uid: str) -> str:
    """Return the collision-free graph ID for a StrictDoc requirement."""

    return f"requirement:{uid}"


def capella_node_id(uuid: str) -> str:
    """Return the collision-free graph ID for a Capella element."""

    return f"capella:{uuid}"


def placeholder_node_id(model_id: str, uuid: str) -> str:
    """Return the graph ID for an unresolved architecture UUID."""

    return f"capella-missing:{model_id}:{uuid}"


def _edge_id(origin: str, source: str, target: str, relation: str) -> str:
    value = f"{origin}\0{source}\0{target}\0{relation}".encode()
    return f"{origin}:{hashlib.sha256(value).hexdigest()[:20]}"


class GraphService:
    """Build, filter, traverse, and search the unified project graph."""

    def __init__(
        self,
        requirement_provider: RequirementProvider,
        capella: CapellaAdapter,
        trace_links: TraceLinkRepository,
    ) -> None:
        self.requirement_provider = requirement_provider
        self.capella = capella
        self.trace_links = trace_links

    def build(
        self,
        *,
        focus: str | None = None,
        depth: int = 2,
        sources: set[str] | None = None,
        types: set[str] | None = None,
        relations: set[str] | None = None,
        text: str | None = None,
        path_from: str | None = None,
        path_to: str | None = None,
        max_nodes: int = 500,
    ) -> GraphResult:
        """Return a filtered graph; focus traversal is cycle-safe and depth-limited."""

        if not 1 <= depth <= 4:
            raise ValueError("Graph depth must be between 1 and 4.")
        if max_nodes < 1:
            raise ValueError("max_nodes must be positive.")
        all_nodes, all_edges = self._all()
        node_map = {node.id: node for node in all_nodes}
        normalized_focus = self._normalize_id(focus, node_map) if focus else None
        if focus and normalized_focus is None:
            raise NotFoundError("Graph node", focus)
        selected_ids = set(node_map)
        if normalized_focus:
            selected_ids = self._within_depth(normalized_focus, all_edges, depth)

        needle = text.casefold().strip() if text else None
        filtered: list[GraphNode] = []
        for node in all_nodes:
            if node.id not in selected_ids:
                continue
            if sources and node.source not in sources:
                continue
            if types and node.type not in types:
                continue
            if needle:
                haystack = " ".join(
                    [node.id, node.label, node.type, str(node.metadata.get("path", ""))]
                ).casefold()
                if needle not in haystack:
                    continue
            filtered.append(node)
        total_nodes = len(filtered)
        truncated = total_nodes > max_nodes
        filtered = filtered[:max_nodes]
        visible = {node.id for node in filtered}
        filtered_edges = [
            edge
            for edge in all_edges
            if edge.source in visible
            and edge.target in visible
            and (not relations or edge.relation in relations)
        ]
        path = None
        if path_from and path_to:
            start = self._normalize_id(path_from, node_map)
            end = self._normalize_id(path_to, node_map)
            if start and end:
                path = self.shortest_path(start, end, all_edges)
        return GraphResult(
            nodes=filtered,
            edges=filtered_edges,
            total_nodes=total_nodes,
            total_edges=len(filtered_edges),
            truncated=truncated,
            path=path,
        )

    def full_graph(self) -> GraphResult:
        """Return the full derived graph for analytics services."""

        nodes, edges = self._all()
        return GraphResult(
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
        )

    @staticmethod
    def shortest_path(start: str, end: str, edges: Sequence[GraphEdge]) -> GraphPath | None:
        """Return one deterministic unweighted shortest path, guarding cycles."""

        if start == end:
            return GraphPath(node_ids=[start], edge_ids=[], length=0)
        adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.source].append((edge.target, edge.id))
            adjacency[edge.target].append((edge.source, edge.id))
        for neighbours in adjacency.values():
            neighbours.sort()
        queue: deque[str] = deque([start])
        previous: dict[str, tuple[str, str] | None] = {start: None}
        while queue:
            current = queue.popleft()
            for neighbour, edge_id in adjacency.get(current, []):
                if neighbour in previous:
                    continue
                previous[neighbour] = (current, edge_id)
                if neighbour == end:
                    return GraphService._reconstruct_path(start, end, previous)
                queue.append(neighbour)
        return None

    @staticmethod
    def _reconstruct_path(
        start: str,
        end: str,
        previous: dict[str, tuple[str, str] | None],
    ) -> GraphPath:
        nodes = [end]
        edges: list[str] = []
        current = end
        while current != start:
            predecessor = previous[current]
            assert predecessor is not None
            current, edge_id = predecessor
            nodes.append(current)
            edges.append(edge_id)
        nodes.reverse()
        edges.reverse()
        return GraphPath(node_ids=nodes, edge_ids=edges, length=len(edges))

    @staticmethod
    def _within_depth(start: str, edges: Sequence[GraphEdge], depth: int) -> set[str]:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            adjacency[edge.source].add(edge.target)
            adjacency[edge.target].add(edge.source)
        visited = {start}
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for neighbour in sorted(adjacency.get(current, set())):
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                queue.append((neighbour, current_depth + 1))
        return visited

    @staticmethod
    def _normalize_id(value: str, nodes: dict[str, GraphNode]) -> str | None:
        if value in nodes:
            return value
        candidates = [
            requirement_node_id(value),
            capella_node_id(value),
        ]
        return next((candidate for candidate in candidates if candidate in nodes), None)

    def _all(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        requirements = sorted(self.requirement_provider(), key=lambda item: item.uid)
        nodes: dict[str, GraphNode] = {
            requirement_node_id(requirement.uid): self._requirement_node(requirement)
            for requirement in requirements
        }
        edges: dict[tuple[str, str, str, str], GraphEdge] = {}
        for requirement in requirements:
            source = requirement_node_id(requirement.uid)
            for relation in requirement.relations:
                target = requirement_node_id(relation.value)
                if target not in nodes:
                    continue
                relation_name = relation.role or relation.type
                self._add_edge(
                    edges,
                    origin="strictdoc",
                    source=source,
                    target=target,
                    relation=relation_name,
                    metadata={"document": requirement.document},
                )

        index = self.capella.ensure_loaded()
        if index is not None:
            for element in index.elements:
                nodes[capella_node_id(element.uuid)] = GraphNode(
                    id=capella_node_id(element.uuid),
                    source="capella",
                    type=element.type,
                    label=element.name or element.type,
                    uuid=element.uuid,
                    group=element.layer,
                    metadata={
                        "model_id": element.model_id,
                        "layer": element.layer,
                        "path": " / ".join(element.path),
                    },
                )
                if element.parent_uuid:
                    self._add_edge(
                        edges,
                        origin="capella",
                        source=capella_node_id(element.parent_uuid),
                        target=capella_node_id(element.uuid),
                        relation="contains",
                    )
            for architecture_relation in index.relations:
                self._add_edge(
                    edges,
                    origin="capella",
                    source=capella_node_id(architecture_relation.source_uuid),
                    target=capella_node_id(architecture_relation.target_uuid),
                    relation=architecture_relation.type,
                    metadata={"name": architecture_relation.name},
                )
            for diagram in index.diagrams:
                diagram_id = capella_node_id(diagram.uuid)
                nodes[diagram_id] = GraphNode(
                    id=diagram_id,
                    source="capella",
                    type="Diagram",
                    label=diagram.name,
                    uuid=diagram.uuid,
                    group="DIAGRAM",
                    metadata={
                        "model_id": index.model_id,
                        "diagram_type": diagram.type,
                        "diagram": True,
                    },
                )
                for represented_uuid in diagram.represented_element_uuids:
                    represented_id = capella_node_id(represented_uuid)
                    if represented_id in nodes:
                        self._add_edge(
                            edges,
                            origin="capella",
                            source=represented_id,
                            target=diagram_id,
                            relation="visible_on_diagram",
                        )

        for link in self.trace_links.list_links().items:
            source = requirement_node_id(link.requirement.uid)
            if source not in nodes:
                continue
            target = capella_node_id(link.architecture.uuid)
            if target not in nodes:
                target = placeholder_node_id(link.architecture.model_id, link.architecture.uuid)
                nodes[target] = GraphNode(
                    id=target,
                    source="placeholder",
                    type=link.architecture.type,
                    label=link.architecture.name_snapshot or link.architecture.uuid,
                    uuid=link.architecture.uuid,
                    group="BROKEN" if link.status == "broken_architecture" else "UNAVAILABLE",
                    broken=link.status == "broken_architecture",
                    metadata={
                        "model_id": link.architecture.model_id,
                        "status": link.status,
                    },
                )
            self._add_edge(
                edges,
                origin="trace-link",
                source=source,
                target=target,
                relation=link.relation,
                metadata={"link_id": link.id, "status": link.status},
                explicit_id=f"trace:{link.id}",
            )

        node_values = sorted(
            nodes.values(), key=lambda item: (item.source, item.type, item.label, item.id)
        )
        edge_values = sorted(
            edges.values(),
            key=lambda item: (item.origin, item.relation, item.source, item.target, item.id),
        )
        return node_values, edge_values

    @staticmethod
    def _requirement_node(requirement: Requirement) -> GraphNode:
        return GraphNode(
            id=requirement_node_id(requirement.uid),
            source="strictdoc",
            type=requirement.type or "Requirement",
            label=requirement.title or requirement.uid,
            uid=requirement.uid,
            group=requirement.document_title,
            metadata={
                "mid": requirement.mid,
                "status": requirement.status,
                "priority": requirement.priority,
                "document": requirement.document,
            },
        )

    @staticmethod
    def _add_edge(
        edges: dict[tuple[str, str, str, str], GraphEdge],
        *,
        origin: str,
        source: str,
        target: str,
        relation: str,
        metadata: dict[str, str | int | bool | None] | None = None,
        explicit_id: str | None = None,
    ) -> None:
        if source == target:
            return
        key = (origin, source, target, relation)
        if key in edges:
            return
        edges[key] = GraphEdge(
            id=explicit_id or _edge_id(origin, source, target, relation),
            source=source,
            target=target,
            relation=relation,
            origin=origin,  # type: ignore[arg-type]
            metadata=metadata or {},
        )


def filter_values(value: str | None) -> set[str] | None:
    """Parse a comma-separated API filter into a stable set."""

    if not value:
        return None
    items: Iterable[str] = (item.strip() for item in value.split(","))
    normalized = {item for item in items if item}
    return normalized or None
