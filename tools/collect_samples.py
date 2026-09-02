#!/usr/bin/env python3
"""Collect a small, stable set of verified release samples from export jobs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
EXPORT_ROOT: Final = ROOT / "exports" / "strictdoc"
SAMPLE_ROOT: Final = ROOT / "exports" / "samples"


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of one regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_revision() -> str:
    """Return the canonical StrictDoc source revision used by the backend."""

    sys.path.insert(0, str(ROOT / "backend"))
    from reqpilot.config import load_project_config
    from reqpilot.strictdoc_adapter import StrictDocAdapter

    config = load_project_config(ROOT / "project.yaml")
    return StrictDocAdapter(config, python_executable=sys.executable).calculate_revision()


def preserved_pdf(revision: str) -> Path:
    """Return a verified committed PDF when this run cannot generate one offline."""

    manifest_path = SAMPLE_ROOT / "manifest.json"
    pdf_path = SAMPLE_ROOT / "strictdoc-requirements.pdf"
    if any(path.is_symlink() for path in (SAMPLE_ROOT, manifest_path, pdf_path)):
        raise RuntimeError("Committed PDF fallback contains a symlink.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "PDF export was not requested and no valid committed PDF manifest exists. "
            "Set REQPILOT_CHROMEDRIVER to refresh PDF samples."
        ) from error
    if manifest.get("canonical_revision") != revision:
        raise RuntimeError(
            "Committed PDF belongs to another canonical revision. "
            "Set REQPILOT_CHROMEDRIVER to refresh PDF samples."
        )
    artifact = next(
        (
            item
            for item in manifest.get("artifacts", [])
            if isinstance(item, dict) and item.get("path") == pdf_path.name
        ),
        None,
    )
    if (
        not pdf_path.is_file()
        or not isinstance(artifact, dict)
        or artifact.get("size") != pdf_path.stat().st_size
        or artifact.get("sha256") != sha256(pdf_path)
    ):
        raise RuntimeError("Committed PDF fallback does not match its manifest.")
    print("Reusing verified PDF sample for the unchanged canonical revision.")
    return pdf_path


def latest_job(export_format: str, suffix: str) -> Path:
    """Find the newest job that contains at least one final-format artifact."""

    format_root = EXPORT_ROOT / export_format
    candidates: list[Path] = []
    if format_root.is_dir():
        for candidate in format_root.iterdir():
            if candidate.is_symlink() or not candidate.is_dir():
                continue
            finals = [
                path
                for path in candidate.rglob(f"*{suffix}")
                if path.is_file() and "_cache" not in path.relative_to(candidate).parts
            ]
            if finals:
                candidates.append(candidate)
    if not candidates:
        raise RuntimeError(f"No successful {export_format} job with {suffix} artifacts found.")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def assert_safe_sample_path(path: Path) -> None:
    """Reject symlink components and sample paths outside repository exports."""

    root = ROOT.resolve(strict=True)
    exports = (root / "exports").resolve(strict=True)
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"Sample path escapes repository: {path}") from error
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise RuntimeError(f"Sample path contains a symlink: {cursor}")
    try:
        path.resolve(strict=False).relative_to(exports)
    except ValueError as error:
        raise RuntimeError(f"Sample path escapes exports: {path}") from error


def zip_tree(source: Path, destination: Path) -> None:
    """Create a deterministic ZIP of the native HTML directory."""

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise RuntimeError(f"Refusing symlink in native HTML sample: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            info = zipfile.ZipInfo(relative.as_posix(), (2026, 9, 2, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())


def collect(staging: Path, revision: str) -> list[dict[str, object]]:
    """Copy final artifacts from the latest successful native jobs."""

    html_job = latest_job("html", ".html")
    excel_job = latest_job("excel", ".xlsx")
    json_job = latest_job("json", ".json")
    reqif_job = latest_job("reqif", ".reqif")

    html_roots = [
        path.parent for path in html_job.rglob("index.html") if "_cache" not in path.parts
    ]
    if not html_roots:
        raise RuntimeError("Native HTML job contains no public index.html.")
    zip_tree(min(html_roots, key=lambda path: len(path.parts)), staging / "strictdoc-html.zip")

    if os.environ.get("REQPILOT_CHROMEDRIVER"):
        pdf_job = latest_job("pdf", ".pdf")
        pdf_files = [
            path
            for path in pdf_job.rglob("*.pdf")
            if path.is_file() and "_cache" not in path.relative_to(pdf_job).parts
        ]
        pdf_source = next((path for path in pdf_files if path.name == "bundle.pdf"), None)
        if pdf_source is None:
            raise RuntimeError("Native PDF job contains no bundle.pdf.")
    else:
        pdf_source = preserved_pdf(revision)
    shutil.copy2(pdf_source, staging / "strictdoc-requirements.pdf")

    excel_output = staging / "excel"
    excel_output.mkdir()
    for path in sorted(excel_job.rglob("*.xlsx")):
        if "_cache" not in path.relative_to(excel_job).parts:
            shutil.copy2(path, excel_output / path.name)

    json_source = next(
        path
        for path in sorted(json_job.rglob("index.json"))
        if "_cache" not in path.relative_to(json_job).parts
    )
    reqif_source = next(
        path
        for path in sorted(reqif_job.rglob("*.reqif"))
        if "_cache" not in path.relative_to(reqif_job).parts
    )
    shutil.copy2(json_source, staging / "strictdoc-index.json")
    shutil.copy2(reqif_source, staging / "strictdoc-requirements.reqif")

    combined = ROOT / "exports" / "combined" / "reqpilot-combined.html"
    if not combined.is_file() or combined.is_symlink():
        raise RuntimeError("Combined HTML export is missing or unsafe.")
    shutil.copy2(combined, staging / "reqpilot-combined.html")

    artifacts: list[dict[str, object]] = []
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            artifacts.append(
                {
                    "path": path.relative_to(staging).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return artifacts


def main() -> int:
    """Atomically install curated samples and a machine-readable manifest."""

    assert_safe_sample_path(SAMPLE_ROOT)
    revision = canonical_revision()
    SAMPLE_ROOT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".samples-", dir=SAMPLE_ROOT.parent) as temporary:
        staging = Path(temporary)
        artifacts = collect(staging, revision)
        manifest = {
            "schema_version": 1,
            "generated_by": "tools/collect_samples.py",
            "source": "native StrictDoc 0.29.0 export jobs and combined report",
            "canonical_revision": revision,
            "artifacts": artifacts,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        backup = SAMPLE_ROOT.with_name(f".{SAMPLE_ROOT.name}.previous-{os.getpid()}")
        if backup.exists() or backup.is_symlink():
            raise RuntimeError(f"Refusing unexpected sample backup path: {backup}")
        if SAMPLE_ROOT.exists():
            os.replace(SAMPLE_ROOT, backup)
        try:
            os.replace(staging, SAMPLE_ROOT)
        except Exception:
            if backup.exists():
                os.replace(backup, SAMPLE_ROOT)
            raise
        else:
            if backup.exists():
                shutil.rmtree(backup)
    print(f"Collected {len(artifacts)} sample artifacts in {SAMPLE_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
