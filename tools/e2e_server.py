#!/usr/bin/env python3
"""Run ReqPilot for Playwright against an isolated disposable project copy."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Final

import uvicorn

ROOT: Final = Path(__file__).resolve().parents[1]
COPIED_DIRECTORIES: Final = ("requirements", "fixtures")
COPIED_FILES: Final = ("project.yaml", "trace-links.yaml", "deleted-uids.json")


def prepare_project(destination: Path) -> Path:
    """Copy only the canonical inputs needed by a fixture-mode E2E server."""

    for directory in COPIED_DIRECTORIES:
        shutil.copytree(
            ROOT / directory,
            destination / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".strictdoc_cache"),
        )
    for filename in COPIED_FILES:
        shutil.copy2(ROOT / filename, destination / filename)
    return destination / "project.yaml"


def main() -> int:
    """Serve a temporary fixture project until Playwright terminates the process."""

    sys.path.insert(0, str(ROOT / "backend"))
    with tempfile.TemporaryDirectory(prefix="reqpilot-e2e-") as temporary:
        config_path = prepare_project(Path(temporary))
        os.environ["REQPILOT_CONFIG"] = str(config_path)
        port = int(os.environ.get("REQPILOT_E2E_BACKEND_PORT", "18080"))
        from reqpilot.app import create_app

        uvicorn.run(
            create_app(config_path=config_path),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
