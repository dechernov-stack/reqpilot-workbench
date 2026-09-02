"""StrictDoc requirement query, CRUD, and validation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from reqpilot.dependencies import get_services
from reqpilot.errors import ReqPilotError
from reqpilot.models import (
    Requirement,
    RequirementCreate,
    RequirementList,
    RequirementUpdate,
    ValidationResult,
)
from reqpilot.service_container import Services

router = APIRouter(prefix="/api/requirements", tags=["requirements"])
ServicesDep = Annotated[Services, Depends(get_services)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _resolve_revision(body_or_query: str | None, if_match: str | None) -> str:
    if body_or_query is None and if_match is None:
        raise ReqPilotError(
            "revision_required",
            "A revision field/query value or If-Match header is required.",
            428,
        )
    if body_or_query is not None and if_match is not None:
        normalized_header = if_match.strip().removeprefix("W/").strip('"')
        normalized_body = body_or_query.strip().removeprefix("W/").strip('"')
        if normalized_header != normalized_body:
            raise ReqPilotError(
                "revision_mismatch",
                "Body/query revision and If-Match header disagree.",
                400,
            )
    return if_match or body_or_query or ""


@router.get("")
def list_requirements(
    services: ServicesDep,
    text: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    document: str | None = None,
) -> RequirementList:
    """List native requirements with deterministic filters and one revision."""

    return services.strictdoc.list_requirements(
        text=text,
        status=status_filter,
        type_=type_filter,
        document=document,
    )


@router.post("/validate")
def validate_requirements(services: ServicesDep) -> ValidationResult:
    """Run StrictDoc's complete native parser/export validation pipeline."""

    return services.strictdoc.validate()


@router.get("/{uid}")
def get_requirement(uid: str, services: ServicesDep) -> Requirement:
    """Return one native requirement by stable UID."""

    return services.strictdoc.get_requirement(uid)


@router.post("", response_model=Requirement, status_code=status.HTTP_201_CREATED)
def create_requirement(payload: RequirementCreate, services: ServicesDep) -> Requirement:
    """Create a requirement through the StrictDoc model/SDWriter transaction."""

    return services.writer.create(payload)


@router.put("/{uid}", response_model=Requirement)
def update_requirement(
    uid: str,
    payload: RequirementUpdate,
    services: ServicesDep,
    if_match: IfMatch = None,
) -> Requirement:
    """Update a requirement with body revision and/or If-Match concurrency."""

    revision = _resolve_revision(payload.revision, if_match)
    effective = payload.model_copy(update={"revision": revision})
    return services.writer.update(uid, effective)


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement(
    uid: str,
    services: ServicesDep,
    if_match: IfMatch = None,
    revision: str | None = None,
) -> Response:
    """Delete a requirement after optimistic and native validation checks."""

    expected = _resolve_revision(revision, if_match)
    services.writer.delete(uid, revision=expected)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
