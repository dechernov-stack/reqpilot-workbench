"""ASGI entry point kept stable for Uvicorn and packaging."""

from reqpilot.app import app, create_app

__all__ = ["app", "create_app"]
