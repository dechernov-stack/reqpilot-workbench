"""Generate the autonomous combined HTML report from canonical adapters."""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape

from reqpilot.adapters.capella import CapellaAdapter
from reqpilot.adapters.trace_links import TraceLinkRepository
from reqpilot.config import ProjectConfig
from reqpilot.models import Requirement
from reqpilot.strictdoc_adapter import StrictDocAdapter

REPORT_CSS = """
:root{color-scheme:light;--ink:#13232d;--muted:#556a75;--line:#ccd9df;
--panel:#f5f8f9;--accent:#0e6675;--ok:#167347;--warn:#9a5b00;--bad:#a52a2a}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);
font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}main{max-width:1480px;margin:auto;
padding:32px}h1{font-size:28px;margin:0 0 4px}h2{font-size:19px;margin:30px 0 10px}
p{margin:6px 0}.muted{color:var(--muted)}.banner{border:2px solid #a86300;
background:#fff8e6;padding:12px 16px;margin:20px 0;font-weight:700}.cards{display:grid;
grid-template-columns:repeat(6,minmax(130px,1fr));gap:10px}.card{background:var(--panel);
border:1px solid var(--line);border-radius:8px;padding:13px}.card b{display:block;
font-size:23px}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:12px}th,td{border:1px solid var(--line);
padding:7px 8px;text-align:left;vertical-align:top}th{background:#e9f0f2;
position:sticky;top:0}.scroll{max-height:520px;overflow:auto;border:1px solid var(--line)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:1px 7px;
margin:1px}.diagrams{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
figure{margin:0;border:1px solid var(--line);padding:10px;border-radius:8px}figure img{width:100%;
height:260px;object-fit:contain;background:#fff}figcaption{font-weight:700;margin-top:8px}
footer{border-top:1px solid var(--line);margin-top:32px;padding-top:14px;color:var(--muted)}
@media print{main{max-width:none;padding:12mm}.scroll{max-height:none;overflow:visible}
th{position:static}.diagrams{grid-template-columns:1fr}.card{break-inside:avoid}}
"""

REPORT_TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>{{ project.title }} — ReqPilot</title>
<style>{{ css }}</style></head><body><main>
<header><h1>{{ project.title }}</h1>
<p class="muted">ReqPilot Engineering Workbench · автономный производный отчёт ·
revision <code>{{ revision }}</code></p></header>
{% if fixture_banner %}<div class="banner">{{ fixture_banner }}</div>{% endif %}
<section><h2>Сводка</h2><div class="cards">
<div class="card"><span>Требования</span><b>{{ requirements|length }}</b></div>
<div class="card"><span>Архитектура</span><b>{{ architecture_count }}</b></div>
<div class="card"><span>Внутренние связи</span><b>{{ relation_count }}</b></div>
<div class="card"><span>Trace links</span><b>{{ links|length }}</b></div>
<div class="card"><span>Тестовое покрытие</span><b>{{ test_coverage }}%</b></div>
<div class="card"><span>Архитектурное покрытие</span><b>{{ architecture_coverage }}%</b></div>
</div></section>
<section><h2>Требования</h2><div class="scroll"><table><thead><tr><th>UID</th><th>MID</th>
<th>Тип</th><th>Статус</th><th>Приоритет</th><th>Название</th><th>Требование</th>
<th>Владелец</th></tr></thead><tbody>{% for item in requirements %}<tr>
<td><b>{{ item.uid }}</b></td><td><code>{{ item.mid }}</code></td><td>{{ item.type or "" }}</td>
<td>{{ item.status or "" }}</td><td>{{ item.priority or "" }}</td><td>{{ item.title or "" }}</td>
<td>{{ item.statement or "" }}</td><td>{{ item.owner or "" }}</td></tr>{% endfor %}
</tbody></table></div></section>
<section><h2>Межсистемная трассировка</h2><div class="scroll"><table><thead><tr>
<th>ID</th><th>Требование</th><th>Связь</th><th>Архитектурный объект</th><th>UUID</th>
<th>Статус</th></tr></thead><tbody>{% for item in links %}<tr>
<td>{{ item.id }}</td><td>{{ item.requirement.uid }}</td><td>{{ item.relation }}</td>
<td>{{ item.current_name or item.architecture.name_snapshot }}</td>
<td><code>{{ item.architecture.uuid }}</code></td>
<td class="{{ 'ok' if item.status == 'valid' else 'bad' }}">{{ item.status }}</td>
</tr>{% endfor %}</tbody></table></div></section>
<section><h2>Непокрытые требования</h2>
<p><b>Тестами:</b> {{ uncovered_tests|join(", ") if uncovered_tests else "нет" }}</p>
<p><b>Архитектурой:</b>
{{ uncovered_architecture|join(", ") if uncovered_architecture else "нет" }}</p>
</section>
<section><h2>Матрица требования ↔ тесты</h2><table><thead><tr><th>Требование</th>
<th>Проверяющие TestCase</th></tr></thead><tbody>{% for row in test_matrix %}<tr>
<td>{{ row.requirement }}</td><td>{{ row.targets|join(", ") or "—" }}</td></tr>{% endfor %}
</tbody></table></section>
<section><h2>Матрица требования ↔ функции</h2><table><thead><tr><th>Требование</th>
<th>Функции</th></tr></thead><tbody>{% for row in function_matrix %}<tr>
<td>{{ row.requirement }}</td><td>{{ row.targets|join(", ") or "—" }}</td></tr>{% endfor %}
</tbody></table></section>
<section><h2>Матрица требования ↔ компоненты</h2><table><thead><tr><th>Требование</th>
<th>Компоненты</th></tr></thead><tbody>{% for row in component_matrix %}<tr>
<td>{{ row.requirement }}</td><td>{{ row.targets|join(", ") or "—" }}</td></tr>{% endfor %}
</tbody></table></section>
<section><h2>Матрица функции ↔ компоненты</h2><table><thead><tr><th>Функция</th>
<th>Компоненты</th></tr></thead><tbody>{% for row in allocation_matrix %}<tr>
<td>{{ row.function }}</td><td>{{ row.components|join(", ") or "—" }}</td></tr>{% endfor %}
</tbody></table></section>
{% if diagrams %}<section><h2>Диаграммы архитектуры</h2><div class="diagrams">
{% for diagram in diagrams %}<figure><img alt="{{ diagram.name }}" src="{{ diagram.data_uri }}">
<figcaption>{{ diagram.name }}</figcaption><p class="muted">{{ diagram.uuid }}</p></figure>
{% endfor %}</div></section>{% endif %}
{% if diagram_errors %}<section><h2>Ошибки диаграмм</h2><ul>
{% for error in diagram_errors %}<li class="bad">{{ error }}</li>{% endfor %}
</ul></section>{% endif %}
<footer><p>Generated from StrictDoc native JSON, read-only {{ architecture_source }} and
trace-links.yaml. This report is not a source of truth.</p>
<p>StrictDoc {{ strictdoc_version }} · capellambse target 0.8.0 · schema 1 ·
fingerprints: requirements {{ revision }}, architecture {{ architecture_fingerprint or "n/a" }},
links {{ link_revision }}</p></footer>
</main></body></html>"""


@dataclass(frozen=True)
class CombinedReportResult:
    """Metadata for one generated standalone report."""

    path: str
    sha256: str
    size: int
    requirement_count: int
    trace_link_count: int
    broken_link_count: int
    test_coverage: float
    architecture_coverage: float

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible result."""

        return asdict(self)


class CombinedReportService:
    """Build one HTML artifact without creating a new canonical data store."""

    def __init__(
        self,
        config: ProjectConfig,
        strictdoc: StrictDocAdapter,
        capella: CapellaAdapter,
        trace_links: TraceLinkRepository,
    ) -> None:
        self.config = config
        self.strictdoc = strictdoc
        self.capella = capella
        self.trace_links = trace_links

    def run(self, output_path: Path | None = None) -> CombinedReportResult:
        """Render and atomically install the current report."""

        destination = self._prepare_output_path(output_path)
        listing = self.strictdoc.list_requirements()
        requirements = listing.items
        architecture = self.capella.ensure_loaded()
        link_listing = self.trace_links.list_links()
        links = link_listing.items
        elements = list(architecture.elements) if architecture is not None else []
        relations = list(architecture.relations) if architecture is not None else []
        by_uuid = {item.uuid: item for item in elements}

        verified = {
            relation.value
            for item in requirements
            if item.type == "TestCase"
            for relation in item.relations
            if relation.role == "Verifies"
        }
        test_scope = [item for item in requirements if item.type in {"System", "Safety"}]
        architecture_scope = [
            item
            for item in requirements
            if item.type in {"System", "Software", "Interface", "Safety"}
        ]
        linked = {item.requirement.uid for item in links if item.status == "valid"}
        test_coverage = self._percent(
            len({item.uid for item in test_scope} & verified),
            len(test_scope),
        )
        architecture_coverage = self._percent(
            len({item.uid for item in architecture_scope} & linked),
            len(architecture_scope),
        )

        trace_targets: dict[str, list[str]] = {}
        trace_target_types: dict[str, list[tuple[str, str]]] = {}
        for link in links:
            element = by_uuid.get(link.architecture.uuid)
            if link.status != "valid" or element is None:
                continue
            trace_targets.setdefault(link.requirement.uid, []).append(element.name)
            trace_target_types.setdefault(link.requirement.uid, []).append(
                (element.type, element.name)
            )
        tests_by_requirement: dict[str, list[str]] = {}
        for test in requirements:
            if test.type != "TestCase":
                continue
            for relation in test.relations:
                if relation.role == "Verifies":
                    tests_by_requirement.setdefault(relation.value, []).append(test.uid)

        function_elements = [item for item in elements if "Function" in item.type]
        allocations: dict[str, list[str]] = {item.uuid: [] for item in function_elements}
        for architecture_relation in relations:
            if architecture_relation.type != "allocated_to":
                continue
            target = by_uuid.get(architecture_relation.target_uuid)
            if target is not None:
                allocations.setdefault(architecture_relation.source_uuid, []).append(target.name)

        diagrams: list[dict[str, str]] = []
        diagram_errors: list[str] = []
        for diagram in self.capella.list_diagrams()[:3]:
            try:
                svg = self.capella.render_diagram(diagram.uuid).encode("utf-8")
            except Exception as error:
                diagram_errors.append(f"{diagram.name}: {error}")
                continue
            diagrams.append(
                {
                    "uuid": diagram.uuid,
                    "name": diagram.name,
                    "data_uri": "data:image/svg+xml;base64,"
                    + base64.b64encode(svg).decode("ascii"),
                }
            )

        context = {
            "css": REPORT_CSS,
            "project": self.config.project,
            "revision": listing.revision,
            "requirements": requirements,
            "architecture_count": len(elements),
            "relation_count": sum(len(item.relations) for item in requirements),
            "links": links,
            "test_coverage": test_coverage,
            "architecture_coverage": architecture_coverage,
            "uncovered_tests": sorted(item.uid for item in test_scope if item.uid not in verified),
            "uncovered_architecture": sorted(
                item.uid for item in architecture_scope if item.uid not in linked
            ),
            "test_matrix": [
                {"requirement": item.uid, "targets": sorted(tests_by_requirement.get(item.uid, []))}
                for item in test_scope
            ],
            "function_matrix": self._trace_matrix(
                architecture_scope, trace_target_types, lambda kind: "Function" in kind
            ),
            "component_matrix": self._trace_matrix(
                architecture_scope, trace_target_types, lambda kind: "Component" in kind
            ),
            "allocation_matrix": [
                {
                    "function": item.name,
                    "components": sorted(set(allocations.get(item.uuid, []))),
                }
                for item in sorted(function_elements, key=lambda value: value.name)
            ],
            "diagrams": diagrams,
            "diagram_errors": diagram_errors,
            "fixture_banner": self.capella.status().banner,
            "architecture_source": (
                architecture.source_kind.value if architecture is not None else "disabled"
            ),
            "architecture_fingerprint": (
                architecture.fingerprint if architecture is not None else None
            ),
            "link_revision": link_listing.revision,
            "strictdoc_version": importlib.metadata.version("strictdoc"),
        }
        environment = Environment(
            autoescape=select_autoescape(default=True),
            undefined=StrictUndefined,
        )
        rendered = environment.from_string(REPORT_TEMPLATE).render(**context)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return CombinedReportResult(
            path=destination.relative_to(self.config.repo_root).as_posix(),
            sha256=digest,
            size=destination.stat().st_size,
            requirement_count=len(requirements),
            trace_link_count=len(links),
            broken_link_count=sum(item.status != "valid" for item in links),
            test_coverage=test_coverage,
            architecture_coverage=architecture_coverage,
        )

    @staticmethod
    def _percent(numerator: int, denominator: int) -> float:
        return round((numerator / denominator * 100) if denominator else 100.0, 1)

    @staticmethod
    def _trace_matrix(
        requirements: list[Requirement],
        targets: dict[str, list[tuple[str, str]]],
        predicate: Callable[[str], bool],
    ) -> list[dict[str, Any]]:
        return [
            {
                "requirement": item.uid,
                "targets": sorted(
                    {name for kind, name in targets.get(item.uid, []) if predicate(kind)}
                ),
            }
            for item in requirements
        ]

    def _prepare_output_path(self, output_path: Path | None) -> Path:
        """Create and validate the generated-output directory without symlinks."""

        root = self.config.repo_root.resolve(strict=True)
        allowed = root / "exports" / "combined"
        requested = output_path or (allowed / "reqpilot-combined.html")
        destination = Path(os.path.abspath(requested))
        try:
            destination.relative_to(allowed)
        except ValueError as error:
            raise ValueError("Combined report path escapes exports/combined.") from error
        if destination == allowed or destination.name in {"", ".", ".."}:
            raise ValueError("Combined report destination must be a file path.")

        self._reject_symlink_components(root, destination.parent)
        if destination.is_symlink():
            raise ValueError("Combined report destination must not be a symlink.")
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Repeat every check after mkdir so a pre-existing or newly introduced
        # symlink can never turn generated output into an out-of-repository write.
        self._reject_symlink_components(root, destination.parent)
        if destination.is_symlink():
            raise ValueError("Combined report destination must not be a symlink.")
        try:
            resolved_parent = destination.parent.resolve(strict=True)
            resolved_allowed = allowed.resolve(strict=True)
            resolved_parent.relative_to(resolved_allowed)
            resolved_parent.relative_to(root)
        except (OSError, ValueError) as error:
            raise ValueError("Combined report path escapes exports/combined.") from error
        if destination.exists() and not destination.is_file():
            raise ValueError("Combined report destination must be a regular file.")
        return resolved_parent / destination.name

    @staticmethod
    def _reject_symlink_components(root: Path, path: Path) -> None:
        """Reject symlinks in an existing lexical path below ``root``."""

        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise ValueError("Combined report path escapes repository root.") from error
        cursor = root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError(f"Combined report path must not contain symlinks: {cursor}.")
