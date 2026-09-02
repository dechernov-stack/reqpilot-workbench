"""Read-only Capella adapter with an explicit fixture/live boundary."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

from lxml import etree  # type: ignore[import-untyped]

from reqpilot.analytics_models import (
    FIXTURE_BANNER,
    CapellaDiagram,
    CapellaElement,
    CapellaIndex,
    CapellaState,
    CapellaStatus,
    SourceKind,
)
from reqpilot.config import ProjectConfig
from reqpilot.errors import NotFoundError, ReqPilotError

MODEL_SUFFIXES: Final = {".aird", ".capella", ".melodymodeller", ".bridgetraces"}
BLOCKED_SVG_ELEMENTS: Final = {
    "script",
    "foreignObject",
    "iframe",
    "object",
    "embed",
    "audio",
    "video",
}

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


class CapellaAdapterError(ReqPilotError):
    """Safe error raised when a Capella source cannot be read."""

    def __init__(self, message: str, *, code: str = "capella_error") -> None:
        super().__init__(code, message, 422)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sanitize_svg(svg: str) -> str:
    """Return safe standalone SVG or reject active/external content.

    Capella output is rendered in the browser.  A strict parser plus a small
    active-content denylist prevents scripts, event handlers, external links,
    and CSS URL loads from crossing that trust boundary.
    """

    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    try:
        root = etree.fromstring(svg.encode("utf-8"), parser=parser)
    except (etree.XMLSyntaxError, ValueError) as error:
        raise CapellaAdapterError(f"Invalid diagram SVG: {error}", code="unsafe_svg") from error
    if etree.QName(root).localname != "svg":
        raise CapellaAdapterError("Diagram payload root is not SVG.", code="unsafe_svg")
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        local_name = etree.QName(element).localname
        if local_name in BLOCKED_SVG_ELEMENTS:
            raise CapellaAdapterError(
                f"Blocked active SVG element: {local_name}.", code="unsafe_svg"
            )
        for raw_name, value in element.attrib.items():
            attribute = etree.QName(raw_name).localname.casefold()
            normalized = value.strip().casefold()
            if attribute.startswith("on"):
                raise CapellaAdapterError(
                    f"Blocked SVG event attribute: {attribute}.", code="unsafe_svg"
                )
            if attribute == "href" and normalized and not normalized.startswith("#"):
                raise CapellaAdapterError("External SVG links are blocked.", code="unsafe_svg")
            safe_fragment_url = (
                normalized.startswith("url(#")
                and normalized.endswith(")")
                and normalized.count("url(") == 1
            )
            if "url(" in normalized and not safe_fragment_url:
                raise CapellaAdapterError("External SVG URL is blocked.", code="unsafe_svg")
            if attribute == "style" and "@import" in normalized:
                raise CapellaAdapterError("External SVG CSS is blocked.", code="unsafe_svg")
        if local_name == "style":
            css = "".join(element.itertext()).casefold()
            if "@import" in css or "url(" in css:
                raise CapellaAdapterError("External SVG CSS is blocked.", code="unsafe_svg")
    return cast(str, etree.tostring(root, encoding="unicode", xml_declaration=False))


class CapellaAdapter:
    """Index Capella through an isolated exact-version worker without saving it."""

    def __init__(
        self,
        config: ProjectConfig,
        *,
        worker_python: str | None = None,
        runner: ProcessRunner = subprocess.run,
        timeout_seconds: float = 120,
    ) -> None:
        self.config = config
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.worker_python = worker_python or self._default_worker_python()
        self.worker_path = Path(__file__).parents[1] / "workers" / "capella_worker.py"
        self._index: CapellaIndex | None = None
        self._fixture_svgs: dict[str, str] = {}
        self._state = self._initial_state()
        self._message = self._initial_message()
        self._last_error: str | None = None

    def _default_worker_python(self) -> str:
        override = os.environ.get("REQPILOT_CAPELLA_PYTHON")
        if override:
            return override
        candidates = [
            Path("/private/tmp/reqpilot-workbench-capella-venv/bin/python"),
            self.config.repo_root / ".venv-capella" / "bin" / "python",
        ]
        if sys.platform == "win32":
            candidates = [self.config.repo_root / ".venv-capella" / "Scripts" / "python.exe"]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return sys.executable

    def _initial_state(self) -> CapellaState:
        if self.config.capella.mode == "disabled":
            return CapellaState.DISABLED
        if self.config.capella.mode == "fixture":
            return CapellaState.FIXTURE
        if not self.config.capella.model_path:
            return CapellaState.NOT_CONFIGURED
        return CapellaState.NOT_CONFIGURED

    def _initial_message(self) -> str:
        if self.config.capella.mode == "disabled":
            return "Capella integration is disabled by project.yaml."
        if self.config.capella.mode == "fixture":
            return FIXTURE_BANNER
        if not self.config.capella.model_path:
            return "Capella live mode has no configured model_path."
        return "Capella model has not been indexed yet."

    @property
    def index(self) -> CapellaIndex | None:
        """Return the current derived index, if one has been loaded."""

        return self._index

    def status(self) -> CapellaStatus:
        """Return current status, detecting a changed live source as stale."""

        state = self._state
        message = self._message
        if self._index is not None and self._index.source_kind == SourceKind.LIVE:
            try:
                current = self._model_fingerprint(self._configured_model_path())
            except (OSError, CapellaAdapterError) as error:
                state = CapellaState.ERROR
                message = str(error)
            else:
                if current != self._index.fingerprint:
                    state = CapellaState.STALE
                    message = "Configured Capella model changed after indexing; reload required."
        index = self._index
        fixture_mode = self.config.capella.mode == "fixture"
        return CapellaStatus(
            state=state,
            mode=self.config.capella.mode,
            message=message,
            model_id=index.model_id if index else None,
            fingerprint=index.fingerprint if index else None,
            element_count=len(index.elements) if index else 0,
            relation_count=len(index.relations) if index else 0,
            diagram_count=len(index.diagrams) if index else 0,
            indexed_duration_ms=index.indexed_duration_ms if index else None,
            fixture=fixture_mode,
            banner=FIXTURE_BANNER if fixture_mode else None,
        )

    def reload(self) -> CapellaIndex | None:
        """Reload a fixture or index a live model through the isolated worker."""

        mode = self.config.capella.mode
        if mode == "disabled":
            self._index = None
            self._state = CapellaState.DISABLED
            self._message = "Capella integration is disabled by project.yaml."
            return None
        self._state = CapellaState.LOADING
        started = time.monotonic()
        try:
            if mode == "fixture":
                index = self._load_fixture()
                self._state = CapellaState.FIXTURE
                self._message = FIXTURE_BANNER
            else:
                index = self._load_live()
                self._state = CapellaState.READY
                self._message = "Capella model indexed read-only."
            index.indexed_duration_ms = int((time.monotonic() - started) * 1000)
            self._index = index
            self._write_cache(index)
            self._last_error = None
            return index
        except Exception as error:
            self._state = CapellaState.ERROR
            self._message = str(error)
            self._last_error = str(error)
            if isinstance(error, ReqPilotError):
                raise
            raise CapellaAdapterError(str(error)) from error

    def ensure_loaded(self) -> CapellaIndex | None:
        """Load on first use while preserving disabled/not-configured semantics."""

        if self._index is not None:
            return self._index
        if self._state == CapellaState.ERROR:
            return None
        if self.config.capella.mode == "disabled":
            return None
        if self.config.capella.mode == "live" and not self.config.capella.model_path:
            self._state = CapellaState.NOT_CONFIGURED
            return None
        return self.reload()

    def list_elements(
        self,
        *,
        layer: str | None = None,
        type_: str | None = None,
        text: str | None = None,
        parent_uuid: str | None = None,
        related_to: str | None = None,
    ) -> list[CapellaElement]:
        """List architecture elements with deterministic filters."""

        index = self.ensure_loaded()
        if index is None:
            return []
        needle = text.casefold().strip() if text else None
        results: list[CapellaElement] = []
        for element in index.elements:
            if layer and element.layer != layer:
                continue
            if type_ and element.type != type_:
                continue
            if parent_uuid and element.parent_uuid != parent_uuid:
                continue
            if related_to and related_to not in element.related_element_uuids:
                continue
            if needle:
                haystack = " ".join(
                    [element.name, element.description or "", " / ".join(element.path)]
                ).casefold()
                if needle not in haystack:
                    continue
            results.append(element)
        return sorted(results, key=lambda item: (item.layer, item.type, item.name, item.uuid))

    def get_element(self, uuid: str) -> CapellaElement:
        """Resolve one architecture element exclusively by UUID."""

        for element in self.list_elements():
            if element.uuid == uuid:
                return element
        raise NotFoundError("Capella element", uuid)

    def list_diagrams(self) -> list[CapellaDiagram]:
        """Return diagram metadata without embedding SVG in the listing."""

        index = self.ensure_loaded()
        if index is None:
            return []
        return sorted(index.diagrams, key=lambda item: (item.name, item.uuid))

    def render_diagram(self, uuid: str) -> str:
        """Render one diagram as sanitized SVG without mutating source files."""

        diagrams = {diagram.uuid: diagram for diagram in self.list_diagrams()}
        if uuid not in diagrams:
            raise NotFoundError("Capella diagram", uuid)
        if self._index is None:
            raise CapellaAdapterError("Architecture index is unavailable.")
        if self._index.source_kind == SourceKind.FIXTURE:
            svg = self._fixture_svgs.get(uuid)
            if svg is None:
                raise CapellaAdapterError(f"Fixture diagram {uuid!r} has no SVG.")
            return sanitize_svg(svg)

        model_path = self._configured_model_path()
        hashes_before = self._model_hashes(model_path)
        payload = self._run_worker("render", diagram_uuid=uuid)
        hashes_after = self._model_hashes(model_path)
        if hashes_before != hashes_after:
            raise CapellaAdapterError(
                "Capella files changed during read-only diagram rendering.",
                code="read_only_violation",
            )
        svg = payload.get("svg")
        if not isinstance(svg, str):
            raise CapellaAdapterError("Capella worker returned no SVG.")
        return sanitize_svg(svg)

    def _load_fixture(self) -> CapellaIndex:
        if not self.config.fixture.enabled:
            raise CapellaAdapterError(
                "Fixture mode requires fixture.enabled=true.", code="fixture_not_enabled"
            )
        path = self.config.resolve_repo_path(self.config.fixture.path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CapellaAdapterError(f"Cannot read architecture fixture: {error}") from error
        raw["source_kind"] = "fixture"
        raw["source_label"] = f"fixture:{path.relative_to(self.config.repo_root)}"
        raw["fingerprint"] = _sha256(path)
        diagrams = raw.get("diagrams", [])
        if isinstance(diagrams, list):
            self._fixture_svgs = {
                str(item["uuid"]): sanitize_svg(str(item["svg"]))
                for item in diagrams
                if isinstance(item, dict) and item.get("uuid") and item.get("svg")
            }
        self._derive_fixture_references(raw)
        try:
            index = CapellaIndex.model_validate(raw)
        except ValueError as error:
            raise CapellaAdapterError(f"Invalid architecture fixture: {error}") from error
        self._validate_index(index)
        return index

    @staticmethod
    def _derive_fixture_references(raw: dict[str, Any]) -> None:
        """Derive redundant fixture lookup fields from its normalized relations."""

        elements_value = raw.get("elements")
        relations_value = raw.get("relations")
        diagrams_value = raw.get("diagrams")
        if not isinstance(elements_value, list):
            return
        elements = {
            str(item["uuid"]): item
            for item in elements_value
            if isinstance(item, dict) and item.get("uuid")
        }
        related: dict[str, set[str]] = {identifier: set() for identifier in elements}
        if isinstance(relations_value, list):
            for relation in relations_value:
                if not isinstance(relation, dict):
                    continue
                source = str(relation.get("source_uuid", ""))
                target = str(relation.get("target_uuid", ""))
                if source in related and target in related:
                    related[source].add(target)
                    related[target].add(source)
        for identifier, item in elements.items():
            parent = item.get("parent_uuid")
            if isinstance(parent, str) and parent in related:
                related[identifier].add(parent)
                related[parent].add(identifier)
            item["related_element_uuids"] = sorted(related[identifier])
            item["diagram_uuids"] = []
        if isinstance(diagrams_value, list):
            for diagram in diagrams_value:
                if not isinstance(diagram, dict) or not diagram.get("uuid"):
                    continue
                diagram_uuid = str(diagram["uuid"])
                represented = diagram.get("represented_element_uuids", [])
                if not isinstance(represented, list):
                    continue
                for identifier in represented:
                    if str(identifier) in elements:
                        elements[str(identifier)]["diagram_uuids"].append(diagram_uuid)
        for item in elements.values():
            item["diagram_uuids"] = sorted(set(item["diagram_uuids"]))

    def _load_live(self) -> CapellaIndex:
        model_path = self._configured_model_path()
        hashes_before = self._model_hashes(model_path)
        payload = self._run_worker("index")
        hashes_after = self._model_hashes(model_path)
        if hashes_before != hashes_after:
            raise CapellaAdapterError(
                "Capella files changed during read-only indexing.", code="read_only_violation"
            )
        payload["source_kind"] = "live"
        payload["source_label"] = str(model_path)
        payload["fingerprint"] = self._fingerprint_hashes(hashes_after)
        try:
            index = CapellaIndex.model_validate(payload)
        except ValueError as error:
            raise CapellaAdapterError(f"Invalid Capella worker index: {error}") from error
        self._validate_index(index)
        return index

    def _configured_model_path(self) -> Path:
        configured = self.config.capella.model_path
        if not configured:
            raise CapellaAdapterError(
                "Capella live mode has no configured model_path.", code="not_configured"
            )
        path = self.config.resolve_repo_path(configured)
        if not path.exists():
            raise CapellaAdapterError(
                f"Configured Capella model does not exist: {path}.", code="not_configured"
            )
        return path

    def _run_worker(self, operation: str, *, diagram_uuid: str | None = None) -> dict[str, Any]:
        model_path = self._configured_model_path()
        command = [
            self.worker_python,
            str(self.worker_path),
            "--operation",
            operation,
            "--model",
            str(model_path),
            "--model-id",
            self.config.project.id,
        ]
        if self.config.capella.entrypoint:
            command.extend(["--entrypoint", self.config.capella.entrypoint])
        if diagram_uuid:
            command.extend(["--diagram-uuid", diagram_uuid])
        try:
            result = self.runner(
                command,
                cwd=self.config.repo_root,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise CapellaAdapterError(
                f"Capella worker timed out after {self.timeout_seconds}s."
            ) from error
        if result.returncode != 0:
            diagnostic = (result.stderr or result.stdout or "unknown worker error").strip()
            raise CapellaAdapterError(f"Capella worker failed: {diagnostic[-20_000:]}")
        try:
            payload: Any = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise CapellaAdapterError("Capella worker returned invalid JSON.") from error
        if not isinstance(payload, dict):
            raise CapellaAdapterError("Capella worker response is not an object.")
        return payload

    def _model_files(self, model_path: Path) -> list[Path]:
        root = model_path if model_path.is_dir() else model_path.parent
        files = [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.casefold() in MODEL_SUFFIXES
        ]
        if model_path.is_file() and model_path not in files:
            files.append(model_path)
        if not files:
            raise CapellaAdapterError(f"No Capella model files found below {root}.")
        return sorted(set(files), key=lambda path: path.as_posix())

    def _model_hashes(self, model_path: Path) -> dict[str, str]:
        root = model_path if model_path.is_dir() else model_path.parent
        return {
            path.relative_to(root).as_posix(): _sha256(path)
            for path in self._model_files(model_path)
        }

    def _model_fingerprint(self, model_path: Path) -> str:
        return self._fingerprint_hashes(self._model_hashes(model_path))

    @staticmethod
    def _fingerprint_hashes(hashes: dict[str, str]) -> str:
        digest = hashlib.sha256()
        for name, value in sorted(hashes.items()):
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(value.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _validate_index(index: CapellaIndex) -> None:
        elements = {element.uuid for element in index.elements}
        if len(elements) != len(index.elements):
            raise CapellaAdapterError("Architecture index contains duplicate element UUIDs.")
        diagrams = {diagram.uuid for diagram in index.diagrams}
        if len(diagrams) != len(index.diagrams):
            raise CapellaAdapterError("Architecture index contains duplicate diagram UUIDs.")
        for element in index.elements:
            if element.model_id != index.model_id:
                raise CapellaAdapterError(f"Element {element.uuid} uses a different model_id.")
            if element.parent_uuid is not None and element.parent_uuid not in elements:
                raise CapellaAdapterError(
                    f"Element {element.uuid} has unknown parent {element.parent_uuid}."
                )
            if not set(element.related_element_uuids) <= elements:
                raise CapellaAdapterError(
                    f"Element {element.uuid} refers to an unknown related UUID."
                )
            if not set(element.diagram_uuids) <= diagrams:
                raise CapellaAdapterError(
                    f"Element {element.uuid} refers to an unknown diagram UUID."
                )
        for relation in index.relations:
            if relation.source_uuid not in elements or relation.target_uuid not in elements:
                raise CapellaAdapterError(
                    f"Architecture relation {relation.type!r} has an unknown endpoint."
                )

    def _write_cache(self, index: CapellaIndex) -> None:
        configured = self.config.capella.cache_path
        repo_root = self.config.repo_root.resolve(strict=True)
        lexical_cache = Path(os.path.abspath(repo_root / configured))
        state_root = repo_root / ".reqpilot"
        try:
            state_relative = lexical_cache.relative_to(state_root)
        except ValueError:
            self.config.reject_repo_path_symlinks(configured)
            cache = self.config.resolve_repo_path(configured)
            cache.parent.mkdir(parents=True, exist_ok=True)
            self.config.reject_repo_path_symlinks(configured)
            cache = self.config.resolve_repo_path(configured)
        else:
            state_parent = self.config.ensure_state_dir(*state_relative.parent.parts)
            cache = state_parent / state_relative.name
        temporary = cache.with_suffix(f"{cache.suffix}.tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, cache)
