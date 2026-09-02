"""Run ReqPilot's local-only FastAPI server."""

from __future__ import annotations

import uvicorn

from reqpilot.config import load_project_config


def main() -> None:
    """Load project.yaml and bind Uvicorn only to configured loopback."""

    config = load_project_config(__import__("pathlib").Path("project.yaml"))
    uvicorn.run(
        "reqpilot.app:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
