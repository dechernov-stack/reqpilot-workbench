"""Synchronous native StrictDoc export jobs and artifact access."""

from __future__ import annotations

import mimetypes
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Final, Literal

from reqpilot.errors import NotFoundError, PathSecurityError
from reqpilot.models import ExportFile, ExportJob
from reqpilot.strictdoc_adapter import StrictDocAdapter, sha256_file

ExportFormat = Literal["html", "pdf", "excel", "json", "reqif"]
EXTRA_ARGS: Final[dict[str, tuple[str, ...]]] = {
    "html": ("--generate-bundle-document",),
    "pdf": ("--generate-bundle-document",),
    "excel": (),
    "json": (),
    "reqif": ("--reqif-enable-mid", "--reqif-multiline-is-xhtml"),
}
NATIVE_FORMAT: Final = {
    "html": "html",
    "pdf": "html2pdf",
    "excel": "excel",
    "json": "json",
    "reqif": "reqif-sdoc",
}
MIME_OVERRIDES: Final = {
    ".reqif": "application/xml",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}
FINAL_SUFFIX: Final[dict[ExportFormat, str]] = {
    "html": ".html",
    "pdf": ".pdf",
    "excel": ".xlsx",
    "json": ".json",
    "reqif": ".reqif",
}


class StrictDocExportService:
    """Run real StrictDoc exports and retain job metadata in process memory."""

    def __init__(self, adapter: StrictDocAdapter) -> None:
        self.adapter = adapter
        self.download_root = self._prepare_generated_directory(
            adapter.config.repo_root / "exports",
            label="repository export root",
        )
        self.root = self._prepare_generated_directory(
            adapter.config.repo_root / adapter.config.strictdoc.export_root,
            label="StrictDoc export root",
        )
        self._jobs: dict[str, ExportJob] = {}
        self._files: dict[str, Path] = {}
        self._guard = threading.Lock()

    def run(self, export_format: ExportFormat) -> ExportJob:
        """Execute one native export synchronously and return its completed job."""

        job_id = uuid.uuid4().hex
        started = time.monotonic()
        with self.adapter.lock:
            revision = self.adapter.calculate_revision()
            job = ExportJob(
                id=job_id,
                format=export_format,
                status="running",
                revision=revision,
            )
            with self._guard:
                self._jobs[job_id] = job
            pdf_driver: Path | None = None
            pdf_error: str | None = None
            if export_format == "pdf":
                pdf_driver, pdf_error = self._pdf_driver()
            if pdf_error is not None:
                job.status = "failed"
                job.error = pdf_error
                job.duration_ms = int((time.monotonic() - started) * 1000)
                with self._guard:
                    self._jobs[job_id] = job
                return job

            output_dir = (self.root / export_format / job_id).resolve()
            self._assert_contained(output_dir)
            output_dir.mkdir(parents=True, exist_ok=False)
            extra_args = EXTRA_ARGS[export_format]
            if pdf_driver is not None:
                extra_args = (*extra_args, "--chromedriver", str(pdf_driver))
            result = self.adapter.run_native_export(
                self.adapter.config.requirements_dir,
                output_dir,
                export_format=NATIVE_FORMAT[export_format],
                extra_args=extra_args,
            )
            revision_after = self.adapter.calculate_revision()
        files = self._index_artifacts(output_dir, export_format=export_format)
        has_final_artifact = any(
            Path(item.name).suffix.lower() == FINAL_SUFFIX[export_format] for item in files
        )
        job.stdout = result.stdout
        job.stderr = result.stderr
        job.command = list(result.command)
        job.returncode = result.returncode
        job.duration_ms = int((time.monotonic() - started) * 1000)
        job.created_files = files
        if revision_after != revision:
            job.status = "failed"
            job.error = (
                "Canonical StrictDoc sources changed during native export "
                f"({revision} -> {revision_after}); artifacts are not a consistent snapshot."
            )
        elif result.returncode == 0 and has_final_artifact:
            job.status = "succeeded"
        else:
            job.status = "failed"
            job.error = (
                result.stderr.strip()
                or result.stdout.strip()
                or (f"StrictDoc export produced no final {FINAL_SUFFIX[export_format]} artifact.")
            )[-20_000:]
        with self._guard:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> ExportJob:
        """Return a known export job."""

        with self._guard:
            job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError("Export job", job_id)
        return job

    def record_job(self, job: ExportJob) -> ExportJob:
        """Register a completed derived-export job for the shared status API."""

        with self._guard:
            self._jobs[job.id] = job
        return job

    def register_artifact(self, path: Path) -> ExportFile:
        """Register one generated file contained by the repository export root."""

        resolved = path.resolve(strict=True)
        self._assert_download_contained(resolved)
        file_id = uuid.uuid4().hex
        media_type = MIME_OVERRIDES.get(
            resolved.suffix.lower(),
            mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
        )
        with self._guard:
            self._files[file_id] = resolved
        return ExportFile(
            id=file_id,
            name=resolved.name,
            path=resolved.relative_to(self.download_root).as_posix(),
            sha256=sha256_file(resolved),
            size=resolved.stat().st_size,
            media_type=media_type,
        )

    def get_file(self, file_id: str) -> tuple[Path, str]:
        """Resolve a generated file ID with strict containment checks."""

        if not file_id or any(character not in "0123456789abcdef" for character in file_id):
            raise PathSecurityError("Export file ID is invalid.")
        with self._guard:
            path = self._files.get(file_id)
        if path is None:
            raise NotFoundError("Export file", file_id)
        resolved = path.resolve(strict=True)
        self._assert_download_contained(resolved)
        media_type = MIME_OVERRIDES.get(
            resolved.suffix.lower(),
            mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
        )
        return resolved, media_type

    def _index_artifacts(
        self, output_dir: Path, *, export_format: ExportFormat
    ) -> list[ExportFile]:
        files: list[ExportFile] = []
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(output_dir)
            if "_cache" in relative.parts:
                continue
            resolved = path.resolve()
            self._assert_contained(resolved)
            artifact = self.register_artifact(resolved)
            artifact = artifact.model_copy(
                update={"path": resolved.relative_to(self.root).as_posix()}
            )
            files.append(artifact)
        return files

    @staticmethod
    def _pdf_driver() -> tuple[Path | None, str | None]:
        """Resolve an explicit local executable to keep PDF export offline."""

        configured = os.environ.get("REQPILOT_CHROMEDRIVER")
        if not configured:
            return None, (
                "PDF export requires REQPILOT_CHROMEDRIVER pointing to an existing "
                "executable; automatic driver download is disabled."
            )
        driver = Path(configured).expanduser().resolve()
        if not driver.is_file() or not os.access(driver, os.X_OK):
            return None, (f"REQPILOT_CHROMEDRIVER does not point to an executable file: {driver}.")
        return driver, None

    def _assert_contained(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self.root)
        except ValueError as error:
            raise PathSecurityError("Export path escapes the configured export root.") from error

    def _assert_download_contained(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self.download_root)
        except ValueError as error:
            raise PathSecurityError("Download path escapes the repository export root.") from error

    def _prepare_generated_directory(self, path: Path, *, label: str) -> Path:
        """Create a repository-local output directory without following symlinks."""

        repo_root = self.adapter.config.repo_root.resolve(strict=True)
        lexical = Path(os.path.abspath(path))
        try:
            relative = lexical.relative_to(repo_root)
        except ValueError as error:
            raise PathSecurityError(f"{label.capitalize()} escapes the repository.") from error
        for attempt in range(2):
            cursor = repo_root
            for part in relative.parts:
                cursor /= part
                if cursor.is_symlink():
                    raise PathSecurityError(f"{label.capitalize()} contains a symlink: {cursor}.")
            if attempt == 0:
                try:
                    lexical.mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    raise PathSecurityError(f"Cannot create {label} safely: {lexical}.") from error
        try:
            resolved = lexical.resolve(strict=True)
            resolved.relative_to(repo_root)
        except (OSError, ValueError) as error:
            raise PathSecurityError(f"{label.capitalize()} is unsafe: {lexical}.") from error
        if not resolved.is_dir():
            raise PathSecurityError(f"{label.capitalize()} is not a directory: {lexical}.")
        return resolved
