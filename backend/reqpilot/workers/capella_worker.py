"""Exact-version, read-only ``capellambse`` worker.

The main StrictDoc runtime cannot contain capellambse 0.8.0 because the two
locked products require incompatible ``python-datauri`` generations.  This
small JSON subprocess is therefore the deliberate process boundary.  It never
calls ``save`` and has no operation capable of writing model files.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final, Protocol, cast

PINNED_CAPELLAMBSE_VERSION: Final = "0.8.0"
LOGGER = logging.getLogger(__name__)

OA_TYPES: Final = {
    "OperationalActivity",
    "OperationalCapability",
    "OperationalProcess",
    "OperationalScenario",
    "Entity",
    "Role",
}
SA_TYPES: Final = {
    "Capability",
    "Mission",
    "SystemAnalysis",
    "SystemComponent",
    "SystemFunction",
}
LA_TYPES: Final = {
    "CapabilityRealization",
    "LogicalArchitecture",
    "LogicalComponent",
    "LogicalFunction",
}
PA_TYPES: Final = {
    "PhysicalArchitecture",
    "PhysicalComponent",
    "PhysicalFunction",
    "PhysicalNode",
}
REFERENCE_ATTRIBUTES: Final = (
    "allocated_functions",
    "allocating_component",
    "components",
    "exchanges",
    "functions",
    "incoming_exchanges",
    "involved",
    "involved_functions",
    "outgoing_exchanges",
    "realized_functions",
    "realizing_functions",
    "source",
    "target",
)


class _HasParent(Protocol):
    parent: object


class _HasTarget(Protocol):
    target: object


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("index", "render"), required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--entrypoint")
    parser.add_argument("--diagram-uuid")
    return parser.parse_args()


def _layer(type_name: str, module_name: str) -> str:
    if type_name in OA_TYPES or ".oa" in module_name:
        return "OA"
    if type_name in SA_TYPES or ".sa" in module_name:
        return "SA"
    if type_name in LA_TYPES or ".la" in module_name:
        return "LA"
    if type_name in PA_TYPES or ".pa" in module_name:
        return "PA"
    if "epbs" in module_name.casefold():
        return "EPBS"
    return "OTHER"


def _safe_text(obj: object, attribute: str) -> str | None:
    try:
        value = getattr(obj, attribute)
    except Exception:
        return None
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def _uuid(obj: object) -> str | None:
    value = _safe_text(obj, "uuid")
    return value if value else None


def _element_iter(value: object) -> Iterable[object]:
    if isinstance(value, str | bytes | dict) or value is None:
        return ()
    if _uuid(value):
        return (value,)
    if not isinstance(value, Iterable):
        return ()
    try:
        return tuple(item for item in value if _uuid(item))
    except (TypeError, AttributeError):
        return ()


def _parent(obj: object) -> object | None:
    try:
        value = cast(_HasParent, obj).parent
    except Exception:
        return None
    return value if _uuid(value) else None


def _path(obj: object) -> list[str]:
    parts: list[str] = []
    seen: set[str] = set()
    current: object | None = obj
    while current is not None:
        identifier = _uuid(current)
        if not identifier or identifier in seen:
            break
        seen.add(identifier)
        name = _safe_text(current, "name")
        if name:
            parts.append(name)
        current = _parent(current)
    return list(reversed(parts))


def _diagram_ids(obj: object) -> list[str]:
    for attribute in ("visible_on_diagrams", "diagrams"):
        try:
            value = getattr(obj, attribute)
        except Exception as error:
            LOGGER.debug("Cannot inspect %s.%s: %s", type(obj).__name__, attribute, error)
            continue
        ids = sorted({identifier for item in _element_iter(value) if (identifier := _uuid(item))})
        if ids:
            return ids
    return []


def _references(obj: object) -> list[tuple[str, str]]:
    references: set[tuple[str, str]] = set()
    for attribute in REFERENCE_ATTRIBUTES:
        if not hasattr(type(obj), attribute):
            continue
        try:
            value = getattr(obj, attribute)
        except Exception as error:
            LOGGER.debug("Cannot inspect %s.%s: %s", type(obj).__name__, attribute, error)
            continue
        for target in _element_iter(value):
            identifier = _uuid(target)
            if identifier and identifier != _uuid(obj):
                references.add((attribute, identifier))
    return sorted(references)


def _load_model(path: Path, entrypoint: str | None) -> Any:
    import capellambse  # type: ignore[import-not-found]

    kwargs: dict[str, object] = {}
    if entrypoint:
        kwargs["entrypoint"] = entrypoint
    return capellambse.MelodyModel(path, **kwargs)


def _diagram_metadata(diagram: object) -> dict[str, object]:
    represented: set[str] = set()
    for attribute in ("semantic_nodes", "nodes"):
        try:
            value = getattr(diagram, attribute)
        except Exception as error:
            LOGGER.debug(
                "Cannot inspect diagram %s.%s: %s", type(diagram).__name__, attribute, error
            )
            continue
        represented.update(
            identifier for item in _element_iter(value) if (identifier := _uuid(item))
        )
    target = None
    with contextlib.suppress(Exception):
        target = cast(_HasTarget, diagram).target
    if identifier := _uuid(target):
        represented.add(identifier)
    return {
        "uuid": _uuid(diagram),
        "name": _safe_text(diagram, "name") or "",
        "type": _safe_text(diagram, "type") or type(diagram).__name__,
        "description": _safe_text(diagram, "description"),
        "represented_element_uuids": sorted(represented),
        "svg_available": True,
    }


def _index(model: Any, model_id: str) -> dict[str, object]:
    objects: dict[str, object] = {}
    diagrams: dict[str, object] = {}
    for obj in model.search():
        identifier = _uuid(obj)
        if not identifier:
            continue
        if hasattr(obj, "render") and type(obj).__name__ in {
            "DRepresentationDescriptor",
            "Diagram",
        }:
            diagrams[identifier] = obj
        else:
            objects[identifier] = obj
    for diagram in model.diagrams:
        if identifier := _uuid(diagram):
            diagrams[identifier] = diagram

    relation_set: set[tuple[str, str, str, str | None]] = set()
    related: dict[str, set[str]] = {identifier: set() for identifier in objects}
    for identifier, obj in objects.items():
        parent = _parent(obj)
        parent_id = _uuid(parent) if parent else None
        if parent_id in objects:
            relation_set.add((parent_id, identifier, "contains", None))
            related[parent_id].add(identifier)
            related[identifier].add(parent_id)
        for relation_type, target_id in _references(obj):
            if target_id not in objects:
                continue
            relation_set.add((identifier, target_id, relation_type, None))
            related[identifier].add(target_id)
            related[target_id].add(identifier)

    elements: list[dict[str, object]] = []
    for identifier, obj in objects.items():
        type_name = type(obj).__name__
        parent = _parent(obj)
        parent_id = _uuid(parent) if parent else None
        elements.append(
            {
                "uuid": identifier,
                "model_id": model_id,
                "type": type_name,
                "layer": _layer(type_name, type(obj).__module__),
                "name": _safe_text(obj, "name") or "",
                "description": _safe_text(obj, "description"),
                "path": _path(obj),
                "parent_uuid": parent_id if parent_id in objects else None,
                "related_element_uuids": sorted(related[identifier]),
                "diagram_uuids": [
                    diagram_id for diagram_id in _diagram_ids(obj) if diagram_id in diagrams
                ],
            }
        )

    relations = [
        {"source_uuid": source, "target_uuid": target, "type": relation, "name": name}
        for source, target, relation, name in sorted(relation_set)
    ]
    diagram_values = [_diagram_metadata(diagram) for _, diagram in sorted(diagrams.items())]
    return {
        "schema_version": 1,
        "model_id": model_id,
        "source_kind": "live",
        "source_label": "capellambse",
        "fingerprint": "worker-defers-to-parent-hash",
        "elements": sorted(
            elements,
            key=lambda item: (
                str(item["layer"]),
                str(item["type"]),
                str(item["name"]),
                str(item["uuid"]),
            ),
        ),
        "relations": relations,
        "diagrams": diagram_values,
        "indexed_duration_ms": 0,
    }


def _render(model: Any, diagram_uuid: str | None) -> dict[str, str]:
    if not diagram_uuid:
        raise ValueError("--diagram-uuid is required for render")
    for diagram in model.diagrams:
        if _uuid(diagram) != diagram_uuid:
            continue
        rendered = diagram.render("svg", pretty_print=True)
        if isinstance(rendered, bytes):
            rendered = rendered.decode("utf-8")
        return {"svg": str(rendered)}
    raise LookupError(f"Diagram {diagram_uuid!r} was not found")


def main() -> int:
    """Run one read-only Capella operation and write a JSON response."""

    actual = importlib.metadata.version("capellambse")
    if actual != PINNED_CAPELLAMBSE_VERSION:
        raise RuntimeError(f"capellambse {PINNED_CAPELLAMBSE_VERSION} required, found {actual}")
    args = _parse_args()
    model = _load_model(args.model, args.entrypoint)
    payload = (
        _index(model, args.model_id)
        if args.operation == "index"
        else _render(model, args.diagram_uuid)
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from error
