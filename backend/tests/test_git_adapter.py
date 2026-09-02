"""Tests for the read-only Git adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

from reqpilot.adapters.git_adapter import GitAdapter


def test_git_status_parses_initial_branch_and_changes(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    def runner(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="## No commits yet on main\n?? project.yaml\n",
            stderr="",
        )

    status = GitAdapter(tmp_path, runner=runner).status()
    assert status.available is True
    assert status.branch == "main"
    assert status.dirty is True
    assert status.changes == ("?? project.yaml",)


def test_git_status_handles_non_repository(tmp_path: Path) -> None:
    status = GitAdapter(tmp_path).status()
    assert status.available is False
    assert status.dirty is False
    assert status.error == "Not a Git repository"
