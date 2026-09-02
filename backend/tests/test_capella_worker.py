"""Pure unit tests for the isolated read-only capellambse worker."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from reqpilot.workers import capella_worker as worker


class SystemAnalysis:
    """Minimal fake model root with a Capella-like public surface."""

    source: object = None
    target: object = None

    def __init__(self, uuid: str, name: str, parent: object | None = None) -> None:
        self.uuid = uuid
        self.name = name
        self.description = f"Description {name}"
        self.parent = parent
        self.visible_on_diagrams: list[object] = []
        self.diagrams: list[object] = []
        self.source = None
        self.target = None


class SystemFunction(SystemAnalysis):
    """Named fake so the worker's type/layer mapping follows the real route."""


class UnknownElement(SystemAnalysis):
    """Reference target deliberately omitted from the fake model search."""


class DRepresentationDescriptor:
    """Minimal fake of capellambse's public diagram descriptor."""

    def __init__(self, uuid: str, represented: list[object], target: object) -> None:
        self.uuid = uuid
        self.name = "System diagram"
        self.type = "System Data Flow Blank"
        self.description = "Diagram description"
        self.semantic_nodes = represented
        self.nodes = represented
        self.target = target

    def render(self, _format: str, *, pretty_print: bool) -> bytes:
        assert pretty_print is True
        return b'<svg xmlns="http://www.w3.org/2000/svg"/>'


class FakeModel:
    """Small connected model; ``save`` is a tripwire and must never run."""

    def __init__(self) -> None:
        self.saved = False
        self.root = SystemAnalysis("root", "Root")
        self.unknown = UnknownElement("outside", "Outside")
        self.function = SystemFunction("function", "Acquire", self.root)
        self.function.source = self.root
        self.function.target = self.unknown
        self.diagram = DRepresentationDescriptor("diagram", [self.function], self.root)
        self.function.visible_on_diagrams = [self.diagram]
        self.diagrams = [self.diagram]

    def search(self) -> list[object]:
        return [self.root, self.function, object(), self.diagram]

    def save(self) -> None:
        self.saved = True
        raise AssertionError("The P0 worker must not call save")


def test_layer_mapping_covers_namespaces_and_fallbacks() -> None:
    assert worker._layer("OperationalActivity", "example") == "OA"
    assert worker._layer("Anything", "capellambse.metamodel.oa") == "OA"
    assert worker._layer("SystemFunction", "example") == "SA"
    assert worker._layer("Anything", "capellambse.metamodel.sa") == "SA"
    assert worker._layer("LogicalFunction", "example") == "LA"
    assert worker._layer("Anything", "capellambse.metamodel.la") == "LA"
    assert worker._layer("PhysicalFunction", "example") == "PA"
    assert worker._layer("Anything", "capellambse.metamodel.pa") == "PA"
    assert worker._layer("Anything", "capellambse.metamodel.epbs") == "EPBS"
    assert worker._layer("Anything", "example") == "OTHER"


def test_safe_access_iter_parent_and_cycle_path_helpers() -> None:
    class BadText:
        def __str__(self) -> str:
            raise ValueError("cannot stringify")

    class Holder:
        none = None
        bad = BadText()

        @property
        def exploding(self) -> object:
            raise RuntimeError("cannot read")

    assert worker._safe_text(Holder(), "missing") is None
    assert worker._safe_text(Holder(), "exploding") is None
    assert worker._safe_text(Holder(), "none") is None
    assert worker._safe_text(Holder(), "bad") is None
    assert list(worker._element_iter("not an element")) == []
    assert list(worker._element_iter(None)) == []
    assert list(worker._element_iter(42)) == []
    element = SystemAnalysis("element", "Element")
    assert list(worker._element_iter(element)) == [element]
    assert list(worker._element_iter([element, object()])) == [element]
    assert worker._parent(object()) is None
    element.parent = element
    assert worker._path(element) == ["Element"]


def test_diagram_and_reference_helpers_tolerate_unavailable_properties() -> None:
    model = FakeModel()

    class FallbackDiagrams(SystemFunction):
        @property
        def visible_on_diagrams(self) -> list[object]:  # type: ignore[override]
            raise RuntimeError("not available")

        @visible_on_diagrams.setter
        def visible_on_diagrams(self, value: list[object]) -> None:
            self._visible = value

    element = FallbackDiagrams("fallback", "Fallback")
    element.diagrams = [model.diagram]
    assert worker._diagram_ids(element) == ["diagram"]
    assert worker._diagram_ids(object()) == []
    assert worker._references(model.function) == [
        ("source", "root"),
        ("target", "outside"),
    ]
    metadata = worker._diagram_metadata(model.diagram)
    assert metadata["uuid"] == "diagram"
    assert metadata["represented_element_uuids"] == ["function", "root"]


def test_index_builds_deterministic_elements_relations_and_diagrams_without_save() -> None:
    model = FakeModel()
    result = worker._index(model, "pump-station")
    assert result["model_id"] == "pump-station"
    assert [item["uuid"] for item in result["elements"]] == [  # type: ignore[index]
        "root",
        "function",
    ]
    relations = result["relations"]
    assert {
        (item["source_uuid"], item["target_uuid"], item["type"])  # type: ignore[index]
        for item in relations  # type: ignore[union-attr]
    } == {
        ("function", "root", "source"),
        ("root", "function", "contains"),
    }
    assert result["diagrams"][0]["uuid"] == "diagram"  # type: ignore[index]
    function = next(item for item in result["elements"] if item["uuid"] == "function")  # type: ignore[index,union-attr]
    assert function["parent_uuid"] == "root"
    assert function["diagram_uuids"] == ["diagram"]
    assert model.saved is False


def test_render_handles_bytes_text_missing_id_and_unknown_diagram() -> None:
    model = FakeModel()
    rendered = worker._render(model, "diagram")
    assert rendered["svg"].startswith("<svg")
    model.diagram.render = lambda *_args, **_kwargs: "<svg/>"  # type: ignore[method-assign]
    assert worker._render(model, "diagram") == {"svg": "<svg/>"}
    with pytest.raises(ValueError, match="diagram-uuid"):
        worker._render(model, None)
    with pytest.raises(LookupError, match="missing"):
        worker._render(model, "missing")


def test_parse_args_and_dynamic_capellambse_loading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worker",
            "--operation",
            "index",
            "--model",
            str(tmp_path),
            "--model-id",
            "model",
            "--entrypoint",
            "main.aird",
        ],
    )
    args = worker._parse_args()
    assert args.operation == "index"
    assert args.model == tmp_path
    assert args.entrypoint == "main.aird"

    calls: list[tuple[Path, dict[str, object]]] = []

    def melody_model(path: Path, **kwargs: object) -> object:
        calls.append((path, kwargs))
        return object()

    monkeypatch.setitem(sys.modules, "capellambse", SimpleNamespace(MelodyModel=melody_model))
    worker._load_model(tmp_path, "main.aird")
    worker._load_model(tmp_path, None)
    assert calls == [
        (tmp_path, {"entrypoint": "main.aird"}),
        (tmp_path, {}),
    ]


def test_main_checks_exact_version_and_dispatches_json(monkeypatch: pytest.MonkeyPatch) -> None:
    model = FakeModel()
    monkeypatch.setattr(worker.importlib.metadata, "version", lambda _name: "0.8.0")
    monkeypatch.setattr(worker, "_load_model", lambda _path, _entrypoint: model)
    monkeypatch.setattr(
        worker,
        "_parse_args",
        lambda: argparse.Namespace(
            operation="index",
            model=Path("model"),
            model_id="pump-station",
            entrypoint="main.aird",
            diagram_uuid=None,
        ),
    )
    output = io.StringIO()
    monkeypatch.setattr(worker.sys, "stdout", output)
    assert worker.main() == 0
    assert json.loads(output.getvalue())["model_id"] == "pump-station"

    monkeypatch.setattr(
        worker,
        "_parse_args",
        lambda: argparse.Namespace(
            operation="render",
            model=Path("model"),
            model_id="pump-station",
            entrypoint=None,
            diagram_uuid="diagram",
        ),
    )
    output = io.StringIO()
    monkeypatch.setattr(worker.sys, "stdout", output)
    assert worker.main() == 0
    assert json.loads(output.getvalue())["svg"].startswith("<svg")

    monkeypatch.setattr(worker.importlib.metadata, "version", lambda _name: "0.8.1")
    with pytest.raises(RuntimeError, match="0.8.0 required"):
        worker.main()
