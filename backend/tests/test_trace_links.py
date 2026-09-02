"""Atomic YAML trace-link validation, CRUD, rename, and broken UUID tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from reqpilot.analytics_models import (
    ArchitectureRef,
    RequirementRef,
    TraceLinkCreate,
    TraceLinkUpdate,
)
from reqpilot.errors import RevisionConflictError, ValidationError

from tests.analytics_support import analytics_stack


def test_checked_in_links_resolve_by_uid_mid_and_uuid(tmp_path: Path, source_repo: Path) -> None:
    _, _, _, repository = analytics_stack(tmp_path, source_repo)
    listing = repository.list_links()
    assert listing.total == 10
    assert {item.status for item in listing.items} == {"valid"}
    validation = repository.validate()
    assert validation.valid is True
    assert validation.diagnostics[0].code == "trace_links_valid"


def test_rename_keeps_uuid_and_id_until_explicit_snapshot_refresh(
    tmp_path: Path, source_repo: Path
) -> None:
    _, _, capella, repository = analytics_stack(tmp_path, source_repo)
    assert capella.index is not None
    target_uuid = "20000000-0000-4000-8000-000000000216"
    capella.index.elements = [
        element.model_copy(update={"name": "Publish Operator State"})
        if element.uuid == target_uuid
        else element
        for element in capella.index.elements
    ]
    before = repository.get("TL-0003")
    assert before.status == "valid"
    assert before.architecture.uuid == target_uuid
    assert before.architecture.name_snapshot == "Publish HMI State"
    assert before.current_name == "Publish Operator State"
    assert before.snapshot_stale is True
    refreshed = repository.refresh_snapshots(revision=repository.revision)
    after = next(item for item in refreshed.items if item.id == "TL-0003")
    assert after.id == before.id
    assert after.architecture.uuid == before.architecture.uuid
    assert after.architecture.name_snapshot == "Publish Operator State"
    assert after.snapshot_stale is False
    assert (tmp_path / "trace-links.yaml.bak").is_file()


def test_deleted_uuid_becomes_broken_and_is_not_removed(tmp_path: Path, source_repo: Path) -> None:
    _, _, capella, repository = analytics_stack(tmp_path, source_repo)
    assert capella.index is not None
    target_uuid = "20000000-0000-4000-8000-000000000213"
    capella.index.elements = [
        element for element in capella.index.elements if element.uuid != target_uuid
    ]
    link = repository.get("TL-0004")
    assert link.status == "broken_architecture"
    assert link.architecture.uuid == target_uuid
    assert repository.list_links().total == 10
    validation = repository.validate()
    assert validation.valid is False
    assert any(item.code == "broken_architecture_uuid" for item in validation.diagnostics)


def test_crud_round_trip_is_atomic_and_revision_checked(tmp_path: Path, source_repo: Path) -> None:
    _, _, _, repository = analytics_stack(tmp_path, source_repo)
    create = TraceLinkCreate(
        requirement=RequirementRef(uid="STK-003", mid="mid_req_stk_003"),
        architecture=ArchitectureRef(
            model_id="pump-station",
            uuid="10000000-0000-4000-8000-000000000112",
            type="OperationalCapability",
            name_snapshot="Review Event History",
        ),
        relation="satisfied_by",
        rationale="История событий реализует потребность заинтересованной стороны.",
        revision=repository.revision,
    )
    created = repository.create(create)
    assert created.id == "TL-0011"
    assert created.status == "valid"
    after_create_revision = repository.revision
    updated = repository.update(
        created.id,
        TraceLinkUpdate(
            rationale="Unicode text: уточнённое обоснование насосной станции.",
            revision=after_create_revision,
        ),
    )
    assert "уточнённое обоснование" in updated.rationale
    assert updated.requirement.uid == "STK-003"
    with pytest.raises(RevisionConflictError):
        repository.delete(created.id, revision=after_create_revision)
    repository.delete(created.id, revision=repository.revision)
    assert repository.list_links().total == 10


def test_invalid_or_duplicate_candidate_never_changes_canonical_yaml(
    tmp_path: Path, source_repo: Path
) -> None:
    _, _, _, repository = analytics_stack(tmp_path, source_repo)
    before = hashlib.sha256(repository.path.read_bytes()).hexdigest()
    invalid = TraceLinkCreate(
        requirement=RequirementRef(uid="MISSING", mid="missing-mid"),
        architecture=ArchitectureRef(
            model_id="pump-station",
            uuid="10000000-0000-4000-8000-000000000112",
            type="OperationalCapability",
            name_snapshot="Review Event History",
        ),
        relation="related_to",
        rationale="Must fail.",
        revision=repository.revision,
    )
    with pytest.raises(ValidationError):
        repository.create(invalid)
    assert hashlib.sha256(repository.path.read_bytes()).hexdigest() == before

    duplicate = TraceLinkCreate(
        requirement=RequirementRef(uid="STK-001", mid="mid_req_stk_001"),
        architecture=ArchitectureRef(
            model_id="pump-station",
            uuid="10000000-0000-4000-8000-000000000110",
            type="OperationalCapability",
            name_snapshot="Monitor Pump Station",
        ),
        relation="satisfied_by",
        rationale="Duplicate pair must fail.",
        revision=repository.revision,
    )
    with pytest.raises(ValidationError) as caught:
        repository.create(duplicate)
    assert caught.value.diagnostics[0]["code"] == "duplicate_pair"
    assert hashlib.sha256(repository.path.read_bytes()).hexdigest() == before


def test_external_trace_edit_during_validation_causes_conflict_without_overwrite(
    tmp_path: Path,
    source_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, repository = analytics_stack(tmp_path, source_repo)
    original_validation = repository._assert_changed_link_valid
    external = repository.path.read_bytes() + b"\n# external writer\n"

    def validate_then_edit(*args: object, **kwargs: object) -> None:
        original_validation(*args, **kwargs)  # type: ignore[arg-type]
        repository.path.write_bytes(external)

    monkeypatch.setattr(repository, "_assert_changed_link_valid", validate_then_edit)
    payload = TraceLinkCreate(
        requirement=RequirementRef(uid="STK-003", mid="mid_req_stk_003"),
        architecture=ArchitectureRef(
            model_id="pump-station",
            uuid="10000000-0000-4000-8000-000000000112",
            type="OperationalCapability",
            name_snapshot="Review Event History",
        ),
        relation="satisfied_by",
        rationale="Must conflict with the external write.",
        revision=repository.revision,
    )

    with pytest.raises(RevisionConflictError) as raised:
        repository.create(payload)

    assert raised.value.status_code == 409
    assert repository.path.read_bytes() == external
