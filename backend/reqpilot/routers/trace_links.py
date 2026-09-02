"""Factory for trace-link YAML CRUD and validation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict

from reqpilot.adapters.trace_links import TraceLinkRepository
from reqpilot.analytics_models import (
    TraceLinkCreate,
    TraceLinkList,
    TraceLinkUpdate,
    TraceLinkView,
    TraceValidationResult,
)
from reqpilot.errors import ReqPilotError

IfMatch = Annotated[str | None, Header(alias="If-Match")]


class RevisionPayload(BaseModel):
    """Optional optimistic revision for snapshot refresh."""

    model_config = ConfigDict(extra="forbid")
    revision: str | None = None


def _revision(value: str | None, if_match: str | None, *, required: bool) -> str | None:
    normalized_header = (
        if_match.strip().removeprefix("W/").strip('"') if if_match is not None else None
    )
    if value is not None and normalized_header is not None and value != normalized_header:
        raise ReqPilotError(
            "revision_mismatch",
            "Body/query revision and If-Match header disagree.",
            400,
        )
    result = normalized_header or value
    if required and result is None:
        raise ReqPilotError(
            "revision_required",
            "A revision or If-Match header is required.",
            428,
        )
    return result


def create_trace_links_router(repository: TraceLinkRepository) -> APIRouter:
    """Create a router bound to one atomic trace-link repository."""

    router = APIRouter(prefix="/api/trace-links", tags=["trace-links"])

    @router.get("")
    def list_links() -> TraceLinkList:
        return repository.list_links()

    @router.post("", response_model=TraceLinkView, status_code=status.HTTP_201_CREATED)
    def create_link(payload: TraceLinkCreate) -> TraceLinkView:
        return repository.create(payload)

    @router.put("/{link_id}", response_model=TraceLinkView)
    def update_link(
        link_id: str,
        payload: TraceLinkUpdate,
        if_match: IfMatch = None,
    ) -> TraceLinkView:
        revision = _revision(payload.revision, if_match, required=True)
        assert revision is not None
        return repository.update(link_id, payload.model_copy(update={"revision": revision}))

    @router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_link(
        link_id: str,
        revision: str | None = Query(default=None),
        if_match: IfMatch = None,
    ) -> Response:
        expected = _revision(revision, if_match, required=True)
        assert expected is not None
        repository.delete(link_id, revision=expected)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/validate")
    def validate_links() -> TraceValidationResult:
        return repository.validate()

    @router.post("/refresh-snapshots")
    def refresh_snapshots(
        payload: RevisionPayload | None = None,
        if_match: IfMatch = None,
    ) -> TraceLinkList:
        revision = _revision(
            payload.revision if payload is not None else None,
            if_match,
            required=False,
        )
        return repository.refresh_snapshots(revision=revision)

    return router
