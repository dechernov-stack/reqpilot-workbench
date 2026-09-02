#!/usr/bin/env python3
"""Run the Stage 0 read-only Capella integration spike.

The spike deliberately does not fall back to fixture data.  A real-model run is
only attempted when ``project.yaml`` selects ``capella.mode: live`` and points
to a local model.  The script never calls ``MelodyModel.save`` and proves that
the configured model tree is byte-for-byte unchanged around load, indexing,
UUID lookup, diagram enumeration, and in-memory SVG rendering.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import sys
import traceback
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

EXPECTED_CAPELLAMBSE_VERSION = "0.8.0"
EXPECTED_CAPELLA_VERSION = "7.1.0"
REAL_TEST_NOT_EXECUTED = "REAL CAPELLA TEST: NOT EXECUTED"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of *path* without modifying it."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_tree(root: Path) -> dict[str, dict[str, int | str]]:
    """Hash every regular file below the configured model root."""

    snapshot: dict[str, dict[str, int | str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        snapshot[relative_path] = {
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return snapshot


def changed_files(
    before: Mapping[str, Mapping[str, int | str]],
    after: Mapping[str, Mapping[str, int | str]],
) -> list[str]:
    """List files that were created, removed, resized, or changed."""

    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )


def load_project_config(path: Path) -> dict[str, Any]:
    """Load ``project.yaml`` using a non-executing safe YAML parser."""

    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def locate_capella_gui() -> list[str]:
    """Return existing Capella GUI candidates without launching them."""

    candidates: set[Path] = set()
    executable = shutil.which("capella")
    if executable:
        candidates.add(Path(executable))

    capella_home = os.environ.get("CAPELLA_HOME")
    if capella_home:
        candidates.add(Path(capella_home).expanduser())

    candidates.update(
        {
            Path("/Applications/Capella.app"),
            Path.home() / "Applications" / "Capella.app",
        }
    )
    return sorted(str(candidate.resolve()) for candidate in candidates if candidate.exists())


def _resolve_local_model(
    project_root: Path,
    raw_model_path: Any,
    raw_entrypoint: Any,
) -> tuple[Path, Path, str | None]:
    """Resolve a local model path and the directory covered by the hash proof."""

    if not isinstance(raw_model_path, str) or not raw_model_path.strip():
        raise ValueError("capella.model_path is not configured")
    if "://" in raw_model_path or raw_model_path.startswith("git@"):
        raise ValueError("Stage 0 proof accepts local Capella models only")

    model_path = Path(raw_model_path).expanduser()
    if not model_path.is_absolute():
        model_path = project_root / model_path
    model_path = model_path.resolve()
    try:
        model_path.relative_to(project_root)
    except ValueError as error:
        raise ValueError("capella.model_path escapes the project root") from error
    if not model_path.exists():
        raise FileNotFoundError(f"Configured Capella model does not exist: {model_path}")

    entrypoint: str | None = None
    if model_path.is_dir():
        model_root = model_path
        if isinstance(raw_entrypoint, str) and raw_entrypoint.strip():
            entrypoint_path = (model_root / raw_entrypoint).resolve()
            try:
                entrypoint_path.relative_to(model_root)
            except ValueError as error:
                raise ValueError("capella.entrypoint escapes capella.model_path") from error
            if not entrypoint_path.is_file():
                raise FileNotFoundError(f"Capella entrypoint does not exist: {entrypoint_path}")
            entrypoint = entrypoint_path.relative_to(model_root).as_posix()
        else:
            aird_files = sorted(model_root.rglob("*.aird"))
            if len(aird_files) != 1:
                raise ValueError(
                    "A directory model_path requires capella.entrypoint unless it contains "
                    "exactly one .aird file"
                )
            entrypoint = aird_files[0].relative_to(model_root).as_posix()
    elif model_path.is_file():
        model_root = model_path.parent
        if raw_entrypoint not in (None, ""):
            raise ValueError("capella.entrypoint must be null when model_path is a file")
    else:
        raise ValueError(f"Unsupported Capella model path: {model_path}")

    return model_path, model_root, entrypoint


def _validate_svg(svg: object) -> tuple[int, str]:
    """Validate an in-memory SVG payload and return byte count and SHA-256."""

    payload = svg if isinstance(svg, bytes) else str(svg).encode("utf-8")
    if b"<svg" not in payload[:4096]:
        raise ValueError("Rendered diagram does not contain an SVG root element")
    return len(payload), hashlib.sha256(payload).hexdigest()


def _safe_attribute(value: object, name: str) -> str | None:
    """Read a display attribute without allowing it to fail the spike."""

    try:
        attribute = getattr(value, name, None)
    except Exception:
        return None
    return str(attribute) if attribute is not None else None


def inspect_live_model(
    *,
    capellambse: Any,
    project_root: Path,
    capella_config: Mapping[str, Any],
    max_diagrams: int,
) -> dict[str, Any]:
    """Load and inspect one configured model while proving read-only behavior."""

    if capella_config.get("read_only") is not True:
        raise ValueError("Refusing live spike because capella.read_only is not true")

    model_path, model_root, entrypoint = _resolve_local_model(
        project_root,
        capella_config.get("model_path"),
        capella_config.get("entrypoint"),
    )
    before = snapshot_tree(model_root)
    if not before:
        raise ValueError(f"Configured model root contains no files: {model_root}")

    inspection: dict[str, Any] = {
        "model_path": str(model_path),
        "model_root": str(model_root),
        "entrypoint": entrypoint,
        "files_hashed_before": len(before),
    }
    primary_error: BaseException | None = None
    try:
        kwargs: dict[str, Any] = {}
        if entrypoint is not None:
            kwargs["entrypoint"] = entrypoint
        model = capellambse.MelodyModel(str(model_path), **kwargs)

        objects = list(model.search())
        uuid_counts: dict[str, int] = {}
        object_types: dict[str, int] = {}
        for model_object in objects:
            uuid = _safe_attribute(model_object, "uuid")
            if uuid:
                uuid_counts[uuid] = uuid_counts.get(uuid, 0) + 1
            type_name = type(model_object).__name__
            object_types[type_name] = object_types.get(type_name, 0) + 1

        duplicate_uuids = sorted(uuid for uuid, count in uuid_counts.items() if count > 1)
        if duplicate_uuids:
            raise ValueError(f"Duplicate UUIDs found: {duplicate_uuids[:10]}")
        if not uuid_counts:
            raise ValueError("The configured model contains no UUID-bearing elements")

        lookup_sample = sorted(uuid_counts)[: min(20, len(uuid_counts))]
        for uuid in lookup_sample:
            model.by_uuid(uuid)

        diagrams = list(model.diagrams)
        diagram_records: list[dict[str, Any]] = []
        render_errors: list[dict[str, str]] = []
        for diagram in diagrams[:max_diagrams]:
            diagram_uuid = _safe_attribute(diagram, "uuid")
            diagram_name = _safe_attribute(diagram, "name")
            try:
                svg_size, svg_sha256 = _validate_svg(diagram.render("svg"))
            except Exception as error:
                render_errors.append(
                    {
                        "uuid": diagram_uuid or "<missing>",
                        "name": diagram_name or "<unnamed>",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
            else:
                diagram_records.append(
                    {
                        "uuid": diagram_uuid,
                        "name": diagram_name,
                        "svg_bytes": svg_size,
                        "svg_sha256": svg_sha256,
                    }
                )

        if not diagrams:
            raise ValueError("The configured real model contains no diagrams")
        if not diagram_records:
            details = "; ".join(item["error"] for item in render_errors[:3])
            raise RuntimeError(f"No diagram could be rendered as SVG: {details}")

        inspection.update(
            {
                "model_uuid": _safe_attribute(model, "uuid"),
                "model_name": _safe_attribute(model, "name"),
                "element_count": len(objects),
                "uuid_count": len(uuid_counts),
                "uuid_lookup_sample_count": len(lookup_sample),
                "element_types": dict(sorted(object_types.items())),
                "diagram_count": len(diagrams),
                "svg_rendered_count": len(diagram_records),
                "rendered_diagrams": diagram_records,
                "render_errors": render_errors,
            }
        )
    except BaseException as error:
        primary_error = error
    finally:
        after = snapshot_tree(model_root)
        changed = changed_files(before, after)
        inspection.update(
            {
                "files_hashed_after": len(after),
                "changed_files": changed,
                "sha256_read_only_proof": not changed,
            }
        )

    if inspection["changed_files"]:
        raise RuntimeError(
            "Capella files changed during read-only inspection: "
            + ", ".join(inspection["changed_files"][:20])
        ) from primary_error
    if primary_error is not None:
        raise primary_error
    return inspection


def build_result(project_root: Path, config_path: Path, max_diagrams: int) -> dict[str, Any]:
    """Build the complete machine-readable Stage 0 result."""

    distribution_version = importlib.metadata.version("capellambse")
    module = importlib.import_module("capellambse")
    module_version = str(getattr(module, "__version__", "<missing>"))
    version_ok = (
        distribution_version == EXPECTED_CAPELLAMBSE_VERSION
        and module_version == EXPECTED_CAPELLAMBSE_VERSION
    )

    result: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "capellambse_distribution_version": distribution_version,
        "capellambse_module_version": module_version,
        "capellambse_expected_version": EXPECTED_CAPELLAMBSE_VERSION,
        "capellambse_version_exact": version_ok,
        "expected_capella_gui_version": EXPECTED_CAPELLA_VERSION,
        "capella_gui_candidates": locate_capella_gui(),
        "config_path": str(config_path),
        "fixture_used": False,
    }
    if not version_ok:
        result.update(
            {
                "status": "FAIL",
                "real_capella_test": "REAL CAPELLA TEST: FAIL",
                "reason": "Exact capellambse 0.8.0 is required",
            }
        )
        return result

    config = load_project_config(config_path)
    capella_config = config.get("capella", {})
    if not isinstance(capella_config, dict):
        raise ValueError("project.yaml capella must be a mapping")
    mode = capella_config.get("mode", "disabled")
    result["capella_mode"] = mode
    result["configured_model_path"] = capella_config.get("model_path")
    result["configured_entrypoint"] = capella_config.get("entrypoint")
    result["configured_read_only"] = capella_config.get("read_only")

    if mode not in {"disabled", "fixture", "live"}:
        result.update(
            {
                "status": "FAIL",
                "real_capella_test": "REAL CAPELLA TEST: FAIL",
                "reason": f"Unsupported capella.mode: {mode!r}",
                "model_inspection": None,
            }
        )
        return result

    if mode != "live":
        reason = (
            "Capella integration is disabled in project.yaml"
            if mode == "disabled"
            else "Fixture mode is not evidence of a real Capella model"
        )
        result.update(
            {
                "status": "NOT EXECUTED",
                "real_capella_test": REAL_TEST_NOT_EXECUTED,
                "reason": reason,
                "model_inspection": None,
            }
        )
        return result

    if not capella_config.get("model_path"):
        result.update(
            {
                "status": "NOT EXECUTED",
                "real_capella_test": REAL_TEST_NOT_EXECUTED,
                "reason": "No real, legally usable Capella model is configured",
                "model_inspection": None,
            }
        )
        return result

    result["model_inspection"] = inspect_live_model(
        capellambse=module,
        project_root=project_root,
        capella_config=capella_config,
        max_diagrams=max_diagrams,
    )
    result.update(
        {
            "status": "PASS",
            "real_capella_test": "REAL CAPELLA TEST: PASS",
            "reason": "Configured real model loaded and remained byte-for-byte unchanged",
        }
    )
    return result


def _markdown_rows(result: Mapping[str, Any]) -> Iterable[tuple[str, str, str]]:
    """Yield concise evidence-table rows for one spike result."""

    exact = result.get("capellambse_version_exact") is True
    yield (
        "capellambse runtime",
        "PASS" if exact else "FAIL",
        f"distribution/module: {result.get('capellambse_distribution_version')} / "
        f"{result.get('capellambse_module_version')}; expected: {EXPECTED_CAPELLAMBSE_VERSION}",
    )
    gui_candidates = result.get("capella_gui_candidates", [])
    yield (
        "Capella GUI",
        "FOUND" if gui_candidates else "NOT FOUND",
        ", ".join(str(path) for path in gui_candidates)
        if gui_candidates
        else "Not found in PATH, CAPELLA_HOME, /Applications, or ~/Applications",
    )
    yield (
        "Real model configuration",
        "CONFIGURED" if result.get("configured_model_path") else "NOT CONFIGURED",
        f"mode={result.get('capella_mode')}; model_path={result.get('configured_model_path')}",
    )
    inspection = result.get("model_inspection")
    if isinstance(inspection, Mapping):
        yield (
            "UUID indexing and lookup",
            "PASS",
            f"{inspection.get('uuid_count')} UUIDs; "
            f"{inspection.get('uuid_lookup_sample_count')} lookups",
        )
        yield (
            "In-memory SVG rendering",
            "PASS",
            f"{inspection.get('svg_rendered_count')} of "
            f"{inspection.get('diagram_count')} diagrams sampled",
        )
        yield (
            "SHA-256 read-only proof",
            "PASS" if inspection.get("sha256_read_only_proof") else "FAIL",
            f"{inspection.get('files_hashed_before')} files before; "
            f"changed={inspection.get('changed_files')}",
        )
    else:
        for check in ("UUID indexing and lookup", "In-memory SVG rendering", "SHA-256 proof"):
            yield (check, "NOT EXECUTED", "No configured real model was opened")


def render_evidence(result: Mapping[str, Any], command: str) -> str:
    """Render an evidence report that cannot confuse fixtures with real data."""

    lines = [
        "# Capella Stage 0 spike",
        "",
        f"Generated: `{result.get('generated_at')}`",
        "",
        f"**{result.get('real_capella_test')}**",
        "",
        "This spike never uses fixture data as evidence for a real Capella run. "
        "It does not invoke `save()` or launch the Capella GUI.",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {check} | {status} | {evidence.replace('|', '\\|')} |"
        for check, status, evidence in _markdown_rows(result)
    )
    lines.extend(["", "## Current outcome", "", str(result.get("reason")), ""])
    if result.get("status") == "NOT EXECUTED":
        lines.extend(
            [
                "No Capella GUI or legally usable real model was supplied to this repository, "
                "so model loading, UUID verification, diagram enumeration, SVG rendering, and "
                "the before/after model hash comparison remain **NOT EXECUTED**. This is an "
                "environment boundary, not a fixture pass.",
                "",
            ]
        )
    elif result.get("status") == "PASS":
        lines.extend(
            [
                "The configured local model was loaded through capellambse, UUIDs were checked, "
                "real diagrams were rendered to SVG in memory, and the model-tree SHA-256 "
                "snapshot was unchanged.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The spike failed and the failure is preserved above and in the machine-readable "
                "result; no fixture result was substituted.",
                "",
            ]
        )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```text",
            command,
            "```",
            "",
            "To perform the real spike later, set `capella.mode: live`, "
            "`capella.model_path`, `capella.entrypoint` when the path is a directory, and keep "
            "`capella.read_only: true`; then rerun the same command with the isolated "
            "`.venv-capella` interpreter.",
            "",
            "## Machine-readable result",
            "",
            "```json",
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--config", type=Path, default=Path("project.yaml"))
    parser.add_argument("--evidence", type=Path, default=Path("evidence/capella-spike.md"))
    parser.add_argument("--max-diagrams", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Execute the spike and return zero for PASS or an honest environment skip."""

    args = parse_args(argv)
    if args.max_diagrams < 1:
        raise SystemExit("--max-diagrams must be at least 1")
    project_root = args.project_root.expanduser().resolve()
    config_path = args.config
    if not config_path.is_absolute():
        config_path = project_root / config_path
    evidence_path = args.evidence
    if not evidence_path.is_absolute():
        evidence_path = project_root / evidence_path

    try:
        result = build_result(project_root, config_path.resolve(), args.max_diagrams)
    except Exception as error:
        result = {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "FAIL",
            "real_capella_test": "REAL CAPELLA TEST: FAIL",
            "reason": f"{type(error).__name__}: {error}",
            "traceback": traceback.format_exc(),
            "fixture_used": False,
        }

    command = ".venv-capella/bin/python tools/spike_capella.py"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(render_evidence(result, command), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
