"""Regression tests for destructive/export packaging CLI safety boundaries."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import reqpilot


def _package_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "release"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "app.py").write_text("pass\n", encoding="utf-8")
    (root / "deleted-uids.json").write_text('{"uids": ["OLD-001"]}\n', encoding="utf-8")
    destination = reqpilot._ensure_confined_directory(root, Path("exports/packages"))
    return root, destination / "bundle.zip"


def test_package_rejects_file_symlink_without_copying_external_bytes(tmp_path: Path) -> None:
    root, archive = _package_root(tmp_path)
    external = tmp_path / "external-secret.txt"
    external.write_text("do-not-package", encoding="utf-8")
    (root / "backend" / "leak.txt").symlink_to(external)

    with pytest.raises(reqpilot.CommandFailure, match="symlink"):
        reqpilot._write_package_archive(root, archive, excluded=set())

    assert not archive.exists()
    assert external.read_text(encoding="utf-8") == "do-not-package"


def test_package_rejects_directory_symlink_and_preserves_external_tree(tmp_path: Path) -> None:
    root, archive = _package_root(tmp_path)
    external = tmp_path / "external-directory"
    external.mkdir()
    secret = external / "secret.txt"
    secret.write_text("do-not-package", encoding="utf-8")
    (root / "backend" / "linked-directory").symlink_to(external, target_is_directory=True)

    with pytest.raises(reqpilot.CommandFailure, match="symlink"):
        reqpilot._write_package_archive(root, archive, excluded=set())

    assert not archive.exists()
    assert secret.read_text(encoding="utf-8") == "do-not-package"


def test_package_allowlist_includes_deleted_uid_registry_not_root_env(tmp_path: Path) -> None:
    root, archive = _package_root(tmp_path)
    (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    reqpilot._write_package_archive(root, archive, excluded=set())

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "deleted-uids.json" in names
        assert "backend/app.py" in names
        assert ".env" not in names


def test_package_uses_curated_samples_and_excludes_generated_caches(tmp_path: Path) -> None:
    root, archive = _package_root(tmp_path)
    (root / "exports" / "samples" / "_cache").mkdir(parents=True)
    (root / "exports" / "samples" / "example.html").write_text("sample", encoding="utf-8")
    (root / "exports" / "samples" / "_cache" / "internal.txt").write_text("cache", encoding="utf-8")
    (root / "exports" / "samples" / ".DS_Store").write_bytes(b"finder")
    (root / "frontend").mkdir()
    (root / "frontend" / "state.tsbuildinfo").write_text("cache", encoding="utf-8")
    (root / "frontend" / "dist").mkdir()
    (root / "frontend" / "dist" / "bundle.js").write_text("generated", encoding="utf-8")
    (root / "backend" / ".mypy_cache").mkdir()
    (root / "backend" / ".mypy_cache" / "state.json").write_text("cache", encoding="utf-8")
    (root / "exports" / "strictdoc").mkdir()
    (root / "exports" / "strictdoc" / "large.html").write_text("generated", encoding="utf-8")

    reqpilot._write_package_archive(root, archive, excluded=set(reqpilot.PACKAGE_RUNTIME_EXCLUDES))

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
    assert "exports/samples/example.html" in names
    assert "exports/samples/_cache/internal.txt" not in names
    assert "exports/samples/.DS_Store" not in names
    assert "frontend/state.tsbuildinfo" not in names
    assert "frontend/dist/bundle.js" not in names
    assert "backend/.mypy_cache/state.json" not in names
    assert "exports/strictdoc/large.html" not in names


def _complete_release_evidence(root: Path) -> None:
    for relative in reqpilot.REQUIRED_RELEASE_EVIDENCE:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n", encoding="utf-8")
    screenshots = root / "evidence" / "screenshots"
    screenshots.mkdir(parents=True)
    for index in range(reqpilot.MINIMUM_RELEASE_SCREENSHOTS):
        (screenshots / f"{index}.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    samples = root / "exports" / "samples"
    artifacts = []
    for relative_name in sorted(reqpilot.REQUIRED_SAMPLE_EXPORTS):
        path = samples / relative_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"sample")
        artifacts.append(
            {
                "path": relative_name,
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (samples / "manifest.json").write_text(
        json.dumps({"canonical_revision": "revision-1", "artifacts": artifacts}),
        encoding="utf-8",
    )


def test_release_evidence_preflight_requires_complete_regular_artifacts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "release"
    root.mkdir()

    with pytest.raises(reqpilot.CommandFailure, match="release evidence"):
        reqpilot._assert_release_evidence(root)

    _complete_release_evidence(root)
    reqpilot._assert_release_evidence(root, expected_revision="revision-1")

    with pytest.raises(reqpilot.CommandFailure, match="canonical source revision"):
        reqpilot._assert_release_evidence(root, expected_revision="revision-2")


def test_release_evidence_preflight_rejects_symlinked_screenshot(tmp_path: Path) -> None:
    root = tmp_path / "release"
    root.mkdir()
    _complete_release_evidence(root)
    external = tmp_path / "external.png"
    external.write_bytes(b"outside")
    screenshot = root / "evidence" / "screenshots" / "0.png"
    screenshot.unlink()
    screenshot.symlink_to(external)

    with pytest.raises(reqpilot.CommandFailure, match="symlinked release evidence"):
        reqpilot._assert_release_evidence(root)


def test_release_evidence_preflight_rejects_jpeg_named_png(tmp_path: Path) -> None:
    root = tmp_path / "release"
    root.mkdir()
    _complete_release_evidence(root)
    (root / "evidence" / "screenshots" / "0.png").write_bytes(b"\xff\xd8\xff\xe0jpeg")

    with pytest.raises(reqpilot.CommandFailure, match="not a PNG"):
        reqpilot._assert_release_evidence(root)


def test_dev_uses_validated_server_config_for_backend_and_proxy(
    isolated_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = isolated_repo / "project.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("port: 8080", "port: 18081"),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def fake_spawn_pair(
        first: list[str],
        second: list[str],
        *,
        second_cwd: Path,
        second_env: dict[str, str] | None = None,
    ) -> int:
        captured.update(
            first=first,
            second=second,
            second_cwd=second_cwd,
            second_env=second_env,
        )
        return 0

    monkeypatch.setattr(reqpilot, "ROOT", isolated_repo)
    monkeypatch.setattr(reqpilot, "BACKEND", isolated_repo / "backend")
    monkeypatch.setattr(reqpilot, "FRONTEND", isolated_repo / "frontend")
    monkeypatch.setattr(reqpilot, "app_python", lambda: Path("python"))
    monkeypatch.setattr(reqpilot, "npm_executable", lambda: "npm")
    monkeypatch.setattr(reqpilot, "_spawn_pair", fake_spawn_pair)

    assert reqpilot.command_dev(object()) == 0
    assert captured["first"][-3:-1] == ["--port", "18081"]
    assert captured["second_env"]["REQPILOT_BACKEND_URL"] == "http://127.0.0.1:18081"


def test_clean_rejects_symlink_to_canonical_requirements(tmp_path: Path) -> None:
    root = tmp_path / "project"
    requirements = root / "requirements"
    requirements.mkdir(parents=True)
    canonical = requirements / "system.sdoc"
    canonical.write_text("canonical", encoding="utf-8")
    (root / "exports").mkdir()
    malicious = root / "exports" / "strictdoc"
    malicious.symlink_to(requirements, target_is_directory=True)

    with pytest.raises(reqpilot.CommandFailure, match="symlinked clean target"):
        reqpilot._clean_paths(root, [malicious], protected={requirements, canonical})

    assert canonical.read_text(encoding="utf-8") == "canonical"
    assert malicious.is_symlink()


def test_cli_validate_rejects_invalid_project_before_native_export(
    isolated_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = isolated_repo / "project.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("host: 127.0.0.1", "host: 0.0.0.0"),
        encoding="utf-8",
    )
    monkeypatch.setattr(reqpilot, "ROOT", isolated_repo)

    with pytest.raises(reqpilot.CommandFailure, match="Invalid project configuration"):
        reqpilot.command_validate(object())


@pytest.mark.parametrize(
    "payload",
    [
        "{}\n",
        '{"uids": ["OLD-001", "OLD-001"]}\n',
        '{"uids": [42]}\n',
        '{"uids": ["not a uid"]}\n',
    ],
)
def test_cli_deleted_uid_registry_validation(
    project_config: Any,
    payload: str,
) -> None:
    config = project_config
    config.deleted_uid_registry_path.write_text(payload, encoding="utf-8")

    assert reqpilot._validate_deleted_uids(config)
