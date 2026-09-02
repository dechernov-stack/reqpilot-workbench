"""Read-only Git status adapter."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class GitStatus:
    """Small immutable Git snapshot for diagnostics and the dashboard."""

    available: bool
    branch: str | None
    dirty: bool
    changes: tuple[str, ...]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        value = asdict(self)
        value["changes"] = list(self.changes)
        return value


class GitAdapter:
    """Inspect branch and worktree state without performing a Git mutation."""

    def __init__(
        self,
        repo_root: Path,
        *,
        runner: Runner = subprocess.run,
        timeout_seconds: float = 10,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    def status(self) -> GitStatus:
        """Return current branch and porcelain changes."""

        if not (self.repo_root / ".git").exists():
            return GitStatus(False, None, False, (), "Not a Git repository")

        try:
            result = self.runner(
                [
                    "git",
                    "-C",
                    str(self.repo_root),
                    "status",
                    "--porcelain=v1",
                    "--branch",
                    "--untracked-files=normal",
                ],
                check=False,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return GitStatus(False, None, False, (), str(error))

        if result.returncode != 0:
            message = result.stderr.strip() or f"git status exited {result.returncode}"
            return GitStatus(False, None, False, (), message)

        lines = result.stdout.splitlines()
        header = lines[0] if lines and lines[0].startswith("## ") else ""
        changes = tuple(line for line in lines if not line.startswith("## "))
        branch = self._branch_from_header(header)
        return GitStatus(True, branch, bool(changes), changes)

    @staticmethod
    def _branch_from_header(header: str) -> str | None:
        if not header:
            return None
        value = header.removeprefix("## ")
        if value.startswith("No commits yet on "):
            return value.removeprefix("No commits yet on ")
        return value.split("...", maxsplit=1)[0].strip() or None
