#!/usr/bin/env python3
"""Generate the ReqPilot standalone combined HTML report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reqpilot.adapters.capella import CapellaAdapter  # noqa: E402
from reqpilot.adapters.trace_links import TraceLinkRepository  # noqa: E402
from reqpilot.config import load_project_config  # noqa: E402
from reqpilot.services.combined_report import CombinedReportService  # noqa: E402
from reqpilot.strictdoc_adapter import StrictDocAdapter  # noqa: E402


def main() -> int:
    config = load_project_config(ROOT / "project.yaml")
    strictdoc = StrictDocAdapter(config)
    capella = CapellaAdapter(config)
    links = TraceLinkRepository(
        config,
        lambda: strictdoc.list_requirements().items,
        capella,
    )
    result = CombinedReportService(config, strictdoc, capella, links).run()
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
