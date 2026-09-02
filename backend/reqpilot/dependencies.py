"""FastAPI dependency accessors."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from reqpilot.service_container import Services


def get_services(request: Request) -> Services:
    """Return this app instance's immutable service container."""

    return cast(Services, request.app.state.services)
