"""Transactional StrictDoc writer integration tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import reqpilot.strictdoc_writer as writer_module
from reqpilot.errors import ReqPilotError, RevisionConflictError, ValidationError
from reqpilot.models import Relation, RequirementCreate, RequirementUpdate
from reqpilot.service_container import Services, build_services
from reqpilot.strictdoc_adapter import sha256_file


def create_payload(revision: str, uid: str = "TC-API-901") -> RequirementCreate:
    return RequirementCreate(
        document="requirements/05_tests.sdoc",
        uid=uid,
        type="TestCase",
        status="Draft",
        priority="Low",
        verification_method="Test",
        owner="Автотест",
        source="pytest",
        tags=["api", " unicode ", "api"],
        title="Проверка безопасной записи",
        statement="Первая строка\nВторая строка: насос ⚙ и Δp.",  # noqa: RUF001
        rationale="Проверяет штатный StrictDoc writer.",
        acceptance_criteria="Проект повторно валиден.",
        comment="Создан интеграционным тестом.",
        relations=[Relation(value="SYS-002", role="Verifies")],
        revision=revision,
    )


def test_update_preserves_mid_relations_and_unicode(services: Services) -> None:
    before = services.strictdoc.get_requirement("SYS-002")
    before_relations = before.relations
    updated = services.writer.update(
        "SYS-002",
        RequirementUpdate(
            revision=before.revision,
            title="Формирование аварии — проверено",
            rationale="Строка один\nСтрока два: насос ⚙, давление Δp",  # noqa: RUF001
            tags=["давление", "проверка"],
        ),
    )
    assert updated.mid == before.mid
    assert updated.uid == before.uid
    assert updated.relations == before_relations
    assert updated.rationale == (
        "Строка один\nСтрока два: насос ⚙, давление Δp\n"  # noqa: RUF001
    )
    assert updated.tags == ["давление", "проверка"]
    assert updated.revision != before.revision
    backups = list((services.config.repo_root / ".reqpilot" / "backups").rglob("*.bak"))
    assert backups


def test_revision_conflict_and_missing_revision(services: Services) -> None:
    current = services.strictdoc.get_requirement("SYS-003")
    with pytest.raises(RevisionConflictError):
        services.writer.update(
            current.uid,
            RequirementUpdate(revision="0" * 64, title="stale"),
        )
    with pytest.raises(ReqPilotError, match="needs revision"):
        services.writer.update(current.uid, RequirementUpdate(title="missing"))


def test_invalid_candidate_rolls_back_without_source_change(services: Services) -> None:
    before = services.strictdoc.get_requirement("SYS-004")
    path = services.config.managed_document(before.document)
    digest = sha256_file(path)
    with pytest.raises(ValidationError, match="canonical sources are unchanged"):
        services.writer.update(
            before.uid,
            RequirementUpdate(revision=before.revision, title=None),
        )
    assert sha256_file(path) == digest
    assert services.strictdoc.get_requirement(before.uid).title == before.title


def test_create_delete_and_no_uid_reuse(services: Services) -> None:
    revision = services.strictdoc.list_requirements().revision
    created = services.writer.create(create_payload(revision))
    assert created.uid == "TC-API-901"
    assert len(created.mid) == 32
    assert created.tags == ["api", "unicode"]
    assert created.relations == [Relation(value="SYS-002", role="Verifies")]
    deleted_revision = services.writer.delete(created.uid, revision=created.revision)
    assert deleted_revision != revision
    registry = services.config.deleted_uid_registry_path
    assert created.uid in registry.read_text(encoding="utf-8")
    restarted = build_services(services.config)
    with pytest.raises(ValidationError, match="cannot be reused"):
        restarted.writer.create(create_payload(deleted_revision))


def test_create_rejects_duplicate_and_unmanaged_document(services: Services) -> None:
    revision = services.strictdoc.list_requirements().revision
    duplicate = create_payload(revision, uid="SYS-001")
    with pytest.raises(ValidationError, match="already exists"):
        services.writer.create(duplicate)
    invalid = create_payload(revision, uid="TC-PATH-001").model_copy(
        update={"document": "../../escape.sdoc"}
    )
    with pytest.raises(Exception, match="not managed"):
        services.writer.create(invalid)


def test_deleting_referenced_uid_is_rejected_and_not_tombstoned(services: Services) -> None:
    requirement = services.strictdoc.get_requirement("STK-001")
    with pytest.raises(ValidationError):
        services.writer.delete(requirement.uid, revision=requirement.revision)
    assert services.strictdoc.get_requirement(requirement.uid).uid == requirement.uid
    tombstone_path = services.config.deleted_uid_registry_path
    if tombstone_path.exists():
        assert requirement.uid not in tombstone_path.read_text(encoding="utf-8")


def test_sha256_streaming(tmp_path: Path) -> None:
    path = tmp_path / "value.txt"
    path.write_text("abc", encoding="utf-8")
    assert sha256_file(path) == ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


def test_external_edit_after_model_load_causes_409_and_is_preserved(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = services.strictdoc.get_requirement("SYS-003")
    path = services.config.managed_document(before.document)
    original_load = services.writer._load_model
    externally_edited = path.read_text(encoding="utf-8").replace(
        f"TITLE: {before.title}",
        f"TITLE: {before.title} — внешняя правка",
        1,
    )

    def load_then_edit() -> tuple[Any, Any]:
        loaded = original_load()
        path.write_text(externally_edited, encoding="utf-8")
        return loaded

    monkeypatch.setattr(services.writer, "_load_model", load_then_edit)
    with pytest.raises(RevisionConflictError) as raised:
        services.writer.update(
            before.uid,
            RequirementUpdate(revision=before.revision, title="ReqPilot update"),
        )

    assert raised.value.status_code == 409
    assert path.read_text(encoding="utf-8") == externally_edited


def test_external_edit_during_candidate_validation_causes_409_and_is_preserved(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = services.strictdoc.get_requirement("SYS-004")
    path = services.config.managed_document(before.document)
    original_export = services.strictdoc.run_native_export
    externally_edited = path.read_text(encoding="utf-8").replace(
        f"TITLE: {before.title}",
        f"TITLE: {before.title} — внешняя правка",
        1,
    )
    injected = False

    def export_then_edit(*args: Any, **kwargs: Any) -> Any:
        nonlocal injected
        result = original_export(*args, **kwargs)
        requirements_dir = Path(args[0]).resolve()
        if not injected and requirements_dir != services.config.requirements_dir.resolve():
            path.write_text(externally_edited, encoding="utf-8")
            injected = True
        return result

    monkeypatch.setattr(services.strictdoc, "run_native_export", export_then_edit)
    with pytest.raises(RevisionConflictError) as raised:
        services.writer.update(
            before.uid,
            RequirementUpdate(revision=before.revision, title="ReqPilot update"),
        )

    assert injected is True
    assert raised.value.status_code == 409
    assert path.read_text(encoding="utf-8") == externally_edited


def test_delete_conflict_during_validation_writes_no_tombstone(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = services.writer.create(
        create_payload(services.strictdoc.list_requirements().revision, uid="TC-CONFLICT-901")
    )
    registry = services.config.deleted_uid_registry_path
    registry_before = registry.read_bytes()
    external_path = services.config.managed_document("01_stakeholder.sdoc")
    external_content = external_path.read_text(encoding="utf-8").replace(
        "VERSION: 1.0", "VERSION: 1.1", 1
    )
    original_export = services.strictdoc.run_native_export
    injected = False

    def export_then_edit(*args: Any, **kwargs: Any) -> Any:
        nonlocal injected
        result = original_export(*args, **kwargs)
        if not injected and Path(args[0]).resolve() != services.config.requirements_dir.resolve():
            external_path.write_text(external_content, encoding="utf-8")
            injected = True
        return result

    monkeypatch.setattr(services.strictdoc, "run_native_export", export_then_edit)
    with pytest.raises(RevisionConflictError) as raised:
        services.writer.delete(created.uid, revision=created.revision)

    assert raised.value.status_code == 409
    assert services.config.managed_document(created.document).read_bytes()
    assert registry.read_bytes() == registry_before
    assert external_path.read_text(encoding="utf-8") == external_content


def test_failed_delete_restores_source_and_exact_registry_state(
    services: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = services.writer.create(
        create_payload(services.strictdoc.list_requirements().revision, uid="TC-ROLLBACK-901")
    )
    source_path = services.config.managed_document(created.document)
    source_before = source_path.read_bytes()
    registry = services.config.deleted_uid_registry_path
    registry_before = b'{\n  "uids": ["OLD-001"]\n}\n'
    registry.write_bytes(registry_before)
    base_revision = services.strictdoc.calculate_revision()
    native_replace = os.replace
    failed_once = False

    def fail_registry_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal failed_once
        source_path_value = Path(source)
        if (
            not failed_once
            and Path(destination) == registry
            and ".reqpilot-" in source_path_value.name
        ):
            failed_once = True
            raise OSError("injected registry replacement failure")
        native_replace(source, destination)

    monkeypatch.setattr(writer_module.os, "replace", fail_registry_replace)
    with pytest.raises(ReqPilotError, match="transaction was rolled back"):
        services.writer.delete(created.uid, revision=base_revision)

    assert failed_once is True
    assert source_path.read_bytes() == source_before
    assert registry.read_bytes() == registry_before
    assert services.strictdoc.calculate_revision() == base_revision


def test_missing_deleted_uid_registry_fails_closed_without_source_change(
    services: Services,
) -> None:
    created = services.writer.create(
        create_payload(services.strictdoc.list_requirements().revision, uid="TC-NOREG-901")
    )
    source_path = services.config.managed_document(created.document)
    source_before = source_path.read_bytes()
    registry = services.config.deleted_uid_registry_path
    registry.unlink()
    base_revision = services.strictdoc.calculate_revision()

    with pytest.raises(ValidationError, match="metadata is missing"):
        services.writer.delete(created.uid, revision=base_revision)

    assert source_path.read_bytes() == source_before
    assert not registry.exists()
    assert services.strictdoc.calculate_revision() == base_revision


@pytest.mark.parametrize("tag", ["one,two", "one\ntwo", "one\rtwo"])
def test_tags_reject_delimiter_characters(tag: str) -> None:
    with pytest.raises(ValueError, match="commas or line breaks"):
        RequirementUpdate(tags=[tag])
