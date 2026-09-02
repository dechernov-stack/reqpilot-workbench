#!/usr/bin/env python3
"""Cross-platform command interface for ReqPilot Engineering Workbench."""

from __future__ import annotations

import argparse
import compileall
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import venv
import zipfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND: Final = ROOT / "backend"
FRONTEND: Final = ROOT / "frontend"
UV_VERSION: Final = "0.8.17"
STRICTDOC_VERSION: Final = "0.29.0"
CAPELLAMBSE_VERSION: Final = "0.8.0"
UID_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
PACKAGE_ROOT_FILES: Final = {
    ".gitignore",
    ".nvmrc",
    ".python-version",
    "CODEX_TASK_ReqPilot_Engineering_Workbench.md",
    "LICENSE",
    "README.md",
    "deleted-uids.json",
    "project.yaml",
    "pyproject.toml",
    "trace-links.yaml",
    "uv.lock",
}
PACKAGE_DIRECTORIES: Final = tuple(
    Path(value)
    for value in (
        ".github",
        "backend",
        "capella",
        "docs",
        "evidence",
        "fixtures",
        "frontend",
        "requirements",
        "tools",
        "exports/combined",
        "exports/samples",
    )
)
PACKAGE_EXCLUDED_NAMES: Final = {".DS_Store", "_cache"}
PACKAGE_EXCLUDED_SUFFIXES: Final = {".tsbuildinfo"}
PACKAGE_RUNTIME_EXCLUDES: Final = {
    ".bootstrap",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".reqpilot",
    ".ruff_cache",
    ".strictdoc_cache",
    ".venv",
    ".venv-capella",
    "__pycache__",
    "coverage",
    "dist",
    "node_modules",
    "output",
    "playwright-report",
    "test-results",
    "tmp",
}
SENSITIVE_PACKAGE_NAMES: Final = {
    ".env",
    ".netrc",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
SENSITIVE_PACKAGE_SUFFIXES: Final = {".key", ".p12", ".pfx", ".pem"}
SENSITIVE_PACKAGE_DIRECTORIES: Final = {".aws", ".gnupg", ".ssh", "secrets"}
REQUIRED_RELEASE_EVIDENCE: Final = (
    Path("evidence/acceptance-report.md"),
    Path("evidence/automated-tests.md"),
    Path("evidence/backend-coverage.xml"),
    Path("evidence/capella-spike.md"),
    Path("evidence/environment.md"),
    Path("evidence/known-limitations.md"),
    Path("evidence/real-capella-test.md"),
    Path("evidence/stage-gates.md"),
    Path("evidence/strictdoc-spike.md"),
)
REQUIRED_SAMPLE_EXPORTS: Final = {
    "excel/01_stakeholder.xlsx",
    "excel/02_system.xlsx",
    "excel/03_software_interface.xlsx",
    "excel/04_safety.xlsx",
    "excel/05_tests.xlsx",
    "reqpilot-combined.html",
    "strictdoc-html.zip",
    "strictdoc-index.json",
    "strictdoc-requirements.pdf",
    "strictdoc-requirements.reqif",
}
MINIMUM_RELEASE_SCREENSHOTS: Final = 3


class CommandFailure(RuntimeError):
    """A user-facing command error with an intended process exit code."""


@dataclass(frozen=True)
class Check:
    """One doctor check."""

    name: str
    status: str
    detail: str
    blocking: bool = False


def _venv_executable(environment: Path, executable: str) -> Path:
    directory = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return environment / directory / f"{executable}{suffix}"


def app_python() -> Path:
    """Return the configured application interpreter."""

    configured = os.environ.get("REQPILOT_PYTHON")
    if configured:
        return Path(os.path.abspath(os.path.expanduser(configured)))
    candidate = _venv_executable(ROOT / ".venv", "python")
    return candidate if candidate.exists() else Path(sys.executable).resolve()


def capella_python() -> Path:
    """Return the isolated capellambse interpreter."""

    configured = os.environ.get("REQPILOT_CAPELLA_PYTHON")
    if configured:
        return Path(os.path.abspath(os.path.expanduser(configured)))
    return _venv_executable(ROOT / ".venv-capella", "python")


def npm_executable() -> str:
    value = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if value is None:
        raise CommandFailure("npm is not available in PATH.")
    return value


def display_command(command: Sequence[str]) -> str:
    """Format an argument vector for logs without executing a shell."""

    import shlex

    return subprocess.list2cmdline(list(command)) if os.name == "nt" else shlex.join(command)


def run(
    command: Sequence[str],
    *,
    cwd: Path = ROOT,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one explicit argument vector with inherited live output."""

    command_list = [str(item) for item in command]
    print(f"$ {display_command(command_list)}", flush=True)
    result = subprocess.run(  # noqa: S603 -- callers provide fixed allowlisted commands.
        command_list,
        cwd=cwd,
        check=False,
        shell=False,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise CommandFailure(
            f"Command exited with {result.returncode}: {display_command(command_list)}"
        )
    return result


def capture(command: Sequence[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Run a diagnostic command and capture its text."""

    return subprocess.run(  # noqa: S603 -- callers provide fixed allowlisted commands.
        [str(item) for item in command],
        cwd=cwd,
        check=False,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


def _load_validated_project() -> Any:
    """Load project.yaml through the backend's single validation boundary."""

    backend_text = str(BACKEND)
    if backend_text in sys.path:
        sys.path.remove(backend_text)
    sys.path.insert(0, backend_text)
    from reqpilot.config import load_project_config

    try:
        return load_project_config(ROOT / "project.yaml")
    except Exception as error:
        raise CommandFailure(f"Invalid project configuration: {error}") from error


def strictdoc_command(*arguments: str) -> list[str]:
    """Build a native StrictDoc CLI invocation resilient to an evicted shim."""

    return [
        str(app_python()),
        "-c",
        "from strictdoc.cli.main import main; main()",
        *arguments,
    ]


def command_setup(_args: argparse.Namespace) -> int:
    """Create both locked Python runtimes and install locked frontend packages."""

    if sys.version_info[:2] != (3, 12):
        raise CommandFailure("setup must be started with Python 3.12.")
    bootstrap = ROOT / ".bootstrap"
    bootstrap_python = _venv_executable(bootstrap, "python")
    uv = _venv_executable(bootstrap, "uv")
    if not uv.exists():
        if not bootstrap_python.exists():
            print("Creating the local bootstrap environment...")
            venv.EnvBuilder(with_pip=True, clear=False).create(bootstrap)
        run(
            [
                str(bootstrap_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                f"uv=={UV_VERSION}",
            ]
        )

    main_env = os.environ.copy()
    main_env["UV_PROJECT_ENVIRONMENT"] = str(ROOT / ".venv")
    run(
        [
            str(uv),
            "sync",
            "--frozen",
            "--python",
            sys.executable,
            "--extra",
            "strictdoc-runtime",
        ],
        env=main_env,
    )
    capella_env = os.environ.copy()
    capella_env["UV_PROJECT_ENVIRONMENT"] = str(ROOT / ".venv-capella")
    run(
        [
            str(uv),
            "sync",
            "--frozen",
            "--python",
            sys.executable,
            "--extra",
            "capella-runtime",
            "--no-dev",
        ],
        env=capella_env,
    )
    run([npm_executable(), "ci"], cwd=FRONTEND)
    return command_doctor(argparse.Namespace())


def _version_check(
    name: str,
    command: Sequence[str],
    expected: str,
    *,
    blocking: bool = True,
) -> Check:
    try:
        result = capture(command)
    except (OSError, subprocess.TimeoutExpired) as error:
        return Check(name, "FAIL" if blocking else "WARN", str(error), blocking)
    observed = (result.stdout or result.stderr).strip()
    passed = result.returncode == 0 and expected in observed
    return Check(
        name,
        "PASS" if passed else ("FAIL" if blocking else "WARN"),
        f"expected {expected}; observed {observed or 'unavailable'}",
        blocking and not passed,
    )


def command_doctor(_args: argparse.Namespace) -> int:
    """Inspect exact versions, paths and local-only configuration."""

    checks: list[Check] = []
    checks.append(
        _version_check(
            "Python",
            [str(app_python()), "--version"],
            "3.12.",
        )
    )
    checks.append(
        _version_check(
            "StrictDoc",
            strictdoc_command("--version"),
            STRICTDOC_VERSION,
        )
    )
    capella = capella_python()
    checks.append(
        _version_check(
            "capellambse",
            [
                str(capella),
                "-c",
                "import importlib.metadata as m; print(m.version('capellambse'))",
            ],
            CAPELLAMBSE_VERSION,
        )
        if capella.exists()
        else Check("capellambse", "FAIL", f"missing interpreter: {capella}", True)
    )
    expected_node = (
        (FRONTEND / ".nvmrc").read_text(encoding="utf-8").strip()
        if (FRONTEND / ".nvmrc").is_file()
        else ""
    )
    node = shutil.which("node")
    checks.append(
        _version_check("Node.js", [node or "node", "--version"], expected_node, blocking=True)
        if node
        else Check("Node.js", "FAIL", "node is not available in PATH", True)
    )
    checks.append(
        Check(
            "frontend lock",
            "PASS" if (FRONTEND / "package-lock.json").is_file() else "FAIL",
            str(FRONTEND / "package-lock.json"),
            not (FRONTEND / "package-lock.json").is_file(),
        )
    )

    python = app_python()
    config_result = capture(
        [
            str(python),
            "-c",
            (
                "import sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(BACKEND)!r}); "
                "from reqpilot.config import load_project_config; "
                f"c=load_project_config(Path({str(ROOT / 'project.yaml')!r})); "
                "print(c.server.host, c.capella.mode, c.capella.read_only)"
            ),
        ]
    )
    config_ok = config_result.returncode == 0 and config_result.stdout.startswith("127.0.0.1 ")
    checks.append(
        Check(
            "project.yaml",
            "PASS" if config_ok else "FAIL",
            (config_result.stdout or config_result.stderr).strip(),
            not config_ok,
        )
    )
    gui_found = any(
        candidate.exists()
        for candidate in (
            Path("/Applications/Capella.app"),
            Path.home() / "Applications" / "Capella.app",
        )
    )
    checks.append(
        Check(
            "Capella GUI",
            "PASS" if gui_found else "WARN",
            "found" if gui_found else "not installed; real manual test remains NOT EXECUTED",
            False,
        )
    )
    driver_value = os.environ.get("REQPILOT_CHROMEDRIVER")
    driver_path = Path(driver_value).expanduser() if driver_value else None
    driver_ok = bool(driver_path and driver_path.is_file() and os.access(driver_path, os.X_OK))
    checks.append(
        Check(
            "PDF chromedriver",
            "PASS" if driver_ok else "WARN",
            str(driver_path.resolve())
            if driver_ok and driver_path is not None
            else "set REQPILOT_CHROMEDRIVER to enable offline PDF export",
            False,
        )
    )
    for item in checks:
        print(f"[{item.status}] {item.name}: {item.detail}")
    failures = [item for item in checks if item.blocking and item.status == "FAIL"]
    print(f"Doctor: {'FAIL' if failures else 'PASS'} ({len(failures)} blocking issue(s))")
    return 1 if failures else 0


def command_validate(_args: argparse.Namespace) -> int:
    """Validate config and canonical sources through native StrictDoc JSON."""

    config = _load_validated_project()
    from reqpilot.strictdoc_adapter import StrictDocAdapter

    try:
        adapter = StrictDocAdapter(config, python_executable=str(app_python()))
        listing = adapter.refresh()
    except Exception as error:
        raise CommandFailure(f"StrictDoc validation/export failed: {error}") from error
    nodes = [{"UID": item.uid, "MID": item.mid} for item in listing.items]
    uids = [str(item.get("UID", "")) for item in nodes]
    mids = [str(item.get("MID", "")) for item in nodes]
    errors: list[str] = []
    if not nodes:
        errors.append("Native StrictDoc JSON contains no requirements.")
    if "" in uids or len(uids) != len(set(uids)):
        errors.append("Requirement UIDs are empty or duplicated.")
    if "" in mids or len(mids) != len(set(mids)):
        errors.append("Requirement MIDs are empty or duplicated.")
    errors.extend(_validate_trace_links(nodes, config))
    errors.extend(_validate_deleted_uids(config))
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print(
        f"[PASS] native StrictDoc validation: {len(nodes)} requirements, "
        f"{len(set(uids))} UIDs, {len(set(mids))} MIDs"
    )
    print("[PASS] project configuration and trace links")
    return 0


def _validate_trace_links(nodes: list[dict[str, Any]], config: Any) -> list[str]:
    path = config.resolve_repo_path(config.trace_links.path)
    if not path.exists():
        return ["trace-links.yaml is missing."]
    try:
        from ruamel.yaml import YAML

        raw = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except Exception as error:
        return [f"trace-links.yaml cannot be parsed: {error}"]
    links = raw.get("links", []) if isinstance(raw, dict) else []
    if not isinstance(links, list):
        return ["trace-links.yaml links must be a list."]
    known_uids = {str(item.get("UID")) for item in nodes}
    known_mids = {str(item.get("MID")) for item in nodes}
    fixture_path = config.resolve_repo_path(config.fixture.path)
    known_architecture: set[tuple[str, str]] = set()
    if fixture_path.is_file():
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture_model = str(fixture.get("model_id", ""))
        known_architecture = {
            (fixture_model, str(item.get("uuid", "")))
            for item in fixture.get("elements", [])
            if isinstance(item, dict)
        }
    errors: list[str] = []
    ids: set[str] = set()
    semantic_keys: set[tuple[str, str, str, str]] = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            errors.append(f"trace link #{index + 1} is not an object.")
            continue
        link_id = str(link.get("id", ""))
        if not link_id or link_id in ids:
            errors.append(f"trace link #{index + 1} has an empty or duplicate id.")
        ids.add(link_id)
        requirement = link.get("requirement", {})
        architecture = link.get("architecture", {})
        if not isinstance(requirement, dict) or not isinstance(architecture, dict):
            errors.append(f"{link_id or index}: requirement/architecture must be objects.")
            continue
        uid = str(
            requirement.get(
                "uid",
                link.get("requirement_uid", link.get("requirementUid", "")),
            )
        )
        mid = str(
            requirement.get(
                "mid",
                link.get("requirement_mid", link.get("requirementMid", "")),
            )
        )
        model_id = str(architecture.get("model_id", link.get("model_id", link.get("modelId", ""))))
        target_uuid = str(
            architecture.get(
                "uuid",
                link.get("target_uuid", link.get("targetUuid", "")),
            )
        )
        relation = str(link.get("relation", ""))
        if uid not in known_uids:
            errors.append(f"{link_id or index}: unknown requirement UID {uid!r}.")
        if mid not in known_mids:
            errors.append(f"{link_id or index}: unknown requirement MID {mid!r}.")
        if known_architecture and (model_id, target_uuid) not in known_architecture:
            errors.append(f"{link_id or index}: unknown fixture architecture UUID {target_uuid!r}.")
        semantic_key = (mid, model_id, target_uuid, relation)
        if semantic_key in semantic_keys:
            errors.append(f"{link_id or index}: duplicate semantic trace-link key.")
        semantic_keys.add(semantic_key)
    return errors


def _validate_deleted_uids(config: Any) -> list[str]:
    path = config.deleted_uid_registry_path
    if not path.is_file() or path.is_symlink():
        return [f"Deleted UID registry is missing or unsafe: {path}."]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"Deleted UID registry cannot be parsed: {error}"]
    values = payload.get("uids") if isinstance(payload, dict) and set(payload) == {"uids"} else None
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not UID_PATTERN.fullmatch(value) for value in values
    ):
        return ["Deleted UID registry must contain a string uids array."]
    if len(values) != len(set(values)):
        return ["Deleted UID registry contains duplicate UIDs."]
    return []


def _spawn_pair(
    first: Sequence[str],
    second: Sequence[str],
    *,
    second_cwd: Path,
    second_env: dict[str, str] | None = None,
) -> int:
    children = [
        subprocess.Popen(  # noqa: S603 -- fixed local development command.
            [str(item) for item in first],
            cwd=ROOT,
            shell=False,
        ),
        subprocess.Popen(  # noqa: S603 -- fixed local development command.
            [str(item) for item in second],
            cwd=second_cwd,
            env=second_env,
            shell=False,
        ),
    ]

    def stop(_signum: int | None = None, _frame: object | None = None) -> None:
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    try:
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
    finally:
        stop()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
    return next((child.returncode for child in children if child.returncode), 0) or 0


def command_dev(_args: argparse.Namespace) -> int:
    """Run FastAPI and Vite on loopback addresses."""

    config = _load_validated_project()
    backend_url = f"http://{config.server.host}:{config.server.port}"
    backend = [
        str(app_python()),
        "-m",
        "uvicorn",
        "reqpilot.main:app",
        "--app-dir",
        "backend",
        "--host",
        str(config.server.host),
        "--port",
        str(config.server.port),
        "--reload",
    ]
    frontend = [npm_executable(), "run", "dev", "--", "--port", "5173"]
    frontend_env = os.environ.copy()
    frontend_env["REQPILOT_BACKEND_URL"] = backend_url
    return _spawn_pair(
        backend,
        frontend,
        second_cwd=FRONTEND,
        second_env=frontend_env,
    )


def command_serve(_args: argparse.Namespace) -> int:
    """Build the frontend and serve the production application locally."""

    config = _load_validated_project()
    command_build(argparse.Namespace())
    return run(
        [
            str(app_python()),
            "-m",
            "uvicorn",
            "reqpilot.main:app",
            "--app-dir",
            "backend",
            "--host",
            str(config.server.host),
            "--port",
            str(config.server.port),
        ]
    ).returncode


def command_strictdoc_serve(_args: argparse.Namespace) -> int:
    """Run StrictDoc's native UI on a separate loopback port."""

    return run(
        strictdoc_command(
            "server",
            "requirements",
            "--config",
            "requirements/strictdoc_config.py",
            "--host",
            "127.0.0.1",
            "--port",
            "5111",
            "--watch",
        )
    ).returncode


def command_index_capella(_args: argparse.Namespace) -> int:
    """Index the configured Capella source through the backend adapter."""

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    code = (
        "from pathlib import Path; "
        "from reqpilot.config import load_project_config; "
        "from reqpilot.adapters.capella import CapellaAdapter; "
        f"c=load_project_config(Path({str(ROOT / 'project.yaml')!r})); "
        "a=CapellaAdapter(c); result=a.reload(); "
        "payload=result.model_dump(mode='json') if result is not None else "
        "a.status().model_dump(mode='json'); "
        "print(__import__('json').dumps(payload, ensure_ascii=False, indent=2))"
    )
    return run([str(app_python()), "-c", code], env=env).returncode


def command_export(args: argparse.Namespace) -> int:
    """Generate native StrictDoc formats and the combined standalone report."""

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    requested = args.formats
    if requested is None:
        requested = ["html", "excel", "json", "reqif"]
        if os.environ.get("REQPILOT_CHROMEDRIVER"):
            requested.insert(1, "pdf")
        else:
            print(
                "[WARN] PDF export NOT EXECUTED: set REQPILOT_CHROMEDRIVER "
                "to an existing executable for offline generation."
            )
    code = (
        "import json; from pathlib import Path; "
        "from reqpilot.config import load_project_config; "
        "from reqpilot.service_container import build_services; "
        f"c=load_project_config(Path({str(ROOT / 'project.yaml')!r})); s=build_services(c); "
        f"formats={requested!r}; "
        "jobs=[s.exports.run(f).model_dump(mode='json') for f in formats]; "
        "print(json.dumps(jobs,ensure_ascii=False,indent=2)); "
        "raise SystemExit(0 if all(j['status']=='succeeded' for j in jobs) else 1)"
    )
    native = run([str(app_python()), "-c", code], env=env, check=False)
    combined_script = ROOT / "tools" / "combined_report.py"
    combined = (
        run([str(app_python()), str(combined_script)], env=env, check=False)
        if combined_script.exists()
        else subprocess.CompletedProcess([], 1)
    )
    return 0 if native.returncode == 0 and combined.returncode == 0 else 1


def command_test(args: argparse.Namespace) -> int:
    """Run backend, frontend and optionally browser tests."""

    run(
        [
            str(app_python()),
            "-m",
            "pytest",
            "backend/tests",
            "--cov=reqpilot",
            "--cov-report=term-missing",
            "--cov-fail-under=85",
        ]
    )
    run([npm_executable(), "run", "test:coverage"], cwd=FRONTEND)
    if not args.no_e2e:
        run([npm_executable(), "run", "test:e2e"], cwd=FRONTEND)
    return 0


def command_build(_args: argparse.Namespace) -> int:
    """Validate Python bytecode and create the production frontend bundle."""

    if not compileall.compile_dir(BACKEND / "reqpilot", quiet=1, force=True):
        raise CommandFailure("Python compilation failed.")
    run([npm_executable(), "run", "lint"], cwd=FRONTEND)
    run([npm_executable(), "run", "build"], cwd=FRONTEND)
    return 0


def command_clean(_args: argparse.Namespace) -> int:
    """Remove only known generated outputs; never touch sources or backups."""

    config = _load_validated_project()
    targets = [
        ROOT / "exports" / "jobs",
        ROOT / "exports" / "strictdoc",
        ROOT / "exports" / "combined",
        ROOT / "output",
        ROOT / ".reqpilot" / "cache",
        ROOT / ".reqpilot" / "staging",
        BACKEND / "htmlcov",
        FRONTEND / "coverage",
        FRONTEND / "dist",
        FRONTEND / "playwright-report",
        FRONTEND / "test-results",
    ]
    protected = {
        config.requirements_dir,
        config.strictdoc_config_path,
        config.deleted_uid_registry_path,
        config.resolve_repo_path(config.trace_links.path),
        *config.managed_document_paths,
    }
    _clean_paths(ROOT, targets, protected=protected)
    return 0


def _clean_paths(root: Path, targets: Sequence[Path], *, protected: set[Path]) -> None:
    """Delete generated lexical paths only after no-follow safety checks."""

    resolved_root = root.resolve(strict=True)
    protected_resolved = {path.resolve(strict=False) for path in protected}
    for target in targets:
        absolute = target.absolute()
        try:
            relative = absolute.relative_to(resolved_root)
        except ValueError as error:
            raise CommandFailure(f"Refusing to clean path outside project: {target}") from error
        cursor = resolved_root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise CommandFailure(f"Refusing symlinked clean target: {relative}")
        resolved = absolute.resolve(strict=False)
        try:
            resolved.relative_to(resolved_root)
        except ValueError as error:
            raise CommandFailure(f"Refusing to clean path outside project: {resolved}") from error
        if resolved == resolved_root:
            raise CommandFailure("Refusing to clean the project root.")
        for canonical in protected_resolved:
            if (
                resolved == canonical
                or canonical in resolved.parents
                or resolved in canonical.parents
            ):
                raise CommandFailure(
                    f"Refusing clean target overlapping canonical source: {relative}"
                )
        if absolute.is_dir():
            shutil.rmtree(absolute)
            print(f"Removed {relative}")
        elif absolute.is_file():
            absolute.unlink()
            print(f"Removed {relative}")


def command_package(args: argparse.Namespace) -> int:
    """Run release gates and create a deterministic source/evidence ZIP."""

    if not args.skip_checks:
        if command_validate(argparse.Namespace()) != 0:
            raise CommandFailure("Validation gate failed.")
        if command_export(argparse.Namespace(formats=None)) != 0:
            raise CommandFailure("Export gate failed.")
        command_test(argparse.Namespace(no_e2e=False))
        command_build(argparse.Namespace())
        sample_env = os.environ.copy()
        sample_env["PYTHONPATH"] = str(BACKEND)
        run([str(app_python()), str(ROOT / "tools" / "collect_samples.py")], env=sample_env)
    else:
        print("Skipping gates and sample refresh; verifying existing curated samples.")
    _assert_release_evidence(ROOT, expected_revision=_canonical_revision())
    destination = _ensure_confined_directory(ROOT, Path("exports/packages"))
    archive = destination / "reqpilot-workbench-p0.zip"
    _write_package_archive(ROOT, archive, excluded=set(PACKAGE_RUNTIME_EXCLUDES))
    print(f"Created {archive} ({archive.stat().st_size} bytes)")
    return 0


def _canonical_revision() -> str:
    """Calculate the current canonical source revision without generating exports."""

    config = _load_validated_project()
    from reqpilot.strictdoc_adapter import StrictDocAdapter

    return StrictDocAdapter(
        config,
        python_executable=str(app_python()),
    ).calculate_revision()


def _assert_release_evidence(root: Path, *, expected_revision: str | None = None) -> None:
    """Fail packaging unless required reports, screenshots and samples are complete."""

    resolved_root = root.resolve(strict=True)

    def assert_regular(relative: Path) -> Path:
        candidate = resolved_root / relative
        cursor = resolved_root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise CommandFailure(f"Refusing symlinked release evidence: {relative}")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError) as error:
            raise CommandFailure(f"Missing or unsafe release evidence: {relative}") from error
        if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
            raise CommandFailure(f"Missing regular release evidence file: {relative}")
        return resolved

    for relative in REQUIRED_RELEASE_EVIDENCE:
        assert_regular(relative)

    screenshot_directory = resolved_root / "evidence" / "screenshots"
    screenshots = sorted(screenshot_directory.glob("*.png"))
    if len(screenshots) < MINIMUM_RELEASE_SCREENSHOTS:
        raise CommandFailure(
            f"Release evidence requires at least {MINIMUM_RELEASE_SCREENSHOTS} PNG screenshots."
        )
    for screenshot in screenshots:
        checked = assert_regular(screenshot.relative_to(resolved_root))
        if checked.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise CommandFailure(f"Release screenshot is not a PNG file: {checked.name}")

    manifest_path = assert_regular(Path("exports/samples/manifest.json"))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["artifacts"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise CommandFailure("Invalid curated sample manifest.") from error
    if not isinstance(entries, list):
        raise CommandFailure("Invalid curated sample manifest artifacts.")
    if expected_revision is not None and manifest.get("canonical_revision") != expected_revision:
        raise CommandFailure("Curated samples do not match the canonical source revision.")
    declared = {
        entry["path"]: entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    missing = REQUIRED_SAMPLE_EXPORTS - declared.keys()
    if missing:
        raise CommandFailure("Curated sample manifest is missing: " + ", ".join(sorted(missing)))
    for relative_name in sorted(REQUIRED_SAMPLE_EXPORTS):
        artifact = assert_regular(Path("exports/samples") / relative_name)
        entry = declared[relative_name]
        if entry.get("size") != artifact.stat().st_size:
            raise CommandFailure(f"Curated sample size mismatch: {relative_name}")
        digest = hashlib.sha256()
        with artifact.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if entry.get("sha256") != digest.hexdigest():
            raise CommandFailure(f"Curated sample SHA-256 mismatch: {relative_name}")


def _ensure_confined_directory(root: Path, relative: Path) -> Path:
    """Create a package output directory without following repository symlinks."""

    resolved_root = root.resolve(strict=True)
    if relative.is_absolute() or ".." in relative.parts:
        raise CommandFailure(f"Unsafe package directory: {relative}")
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise CommandFailure(f"Refusing symlinked package directory: {cursor}")
        try:
            cursor.resolve(strict=False).relative_to(resolved_root)
        except ValueError as error:
            raise CommandFailure(f"Package directory escapes project: {cursor}") from error
    cursor.mkdir(parents=True, exist_ok=True)
    if cursor.is_symlink() or not cursor.is_dir():
        raise CommandFailure(f"Unsafe package directory after creation: {cursor}")
    try:
        resolved = cursor.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise CommandFailure(f"Package directory escapes project: {cursor}") from error
    return resolved


def _iter_package_files(
    root: Path,
    *,
    archive: Path,
    excluded: set[str],
) -> Iterator[tuple[Path, Path]]:
    """Yield regular package files while rejecting symlinks and escapes."""

    resolved_root = root.resolve(strict=True)
    archive_parent = archive.parent.resolve(strict=True)
    for current_name, directory_names, file_names in os.walk(
        resolved_root, topdown=True, followlinks=False
    ):
        current = Path(current_name)
        safe_directories: list[str] = []
        for name in sorted(directory_names):
            candidate = current / name
            relative = candidate.relative_to(resolved_root)
            if name in PACKAGE_EXCLUDED_NAMES:
                continue
            if candidate.is_symlink():
                raise CommandFailure(f"Refusing symlink in package input: {relative}")
            if candidate.resolve(strict=True) == archive_parent:
                continue
            if any(part in excluded for part in relative.parts):
                continue
            if name.casefold() in SENSITIVE_PACKAGE_DIRECTORIES:
                raise CommandFailure(f"Refusing sensitive package directory: {relative}")
            if not _package_directory_allowed(relative):
                continue
            try:
                candidate.resolve(strict=True).relative_to(resolved_root)
            except (OSError, ValueError) as error:
                raise CommandFailure(f"Package directory escapes project: {relative}") from error
            safe_directories.append(name)
        directory_names[:] = safe_directories

        for name in sorted(file_names):
            candidate = current / name
            relative = candidate.relative_to(resolved_root)
            if (
                name in PACKAGE_EXCLUDED_NAMES
                or candidate.suffix.casefold() in PACKAGE_EXCLUDED_SUFFIXES
            ):
                continue
            if candidate.is_symlink():
                raise CommandFailure(f"Refusing symlink in package input: {relative}")
            if any(part in excluded for part in relative.parts):
                continue
            if not _package_file_allowed(relative):
                continue
            normalized_name = name.casefold()
            if (
                normalized_name.startswith(".env")
                or normalized_name in SENSITIVE_PACKAGE_NAMES
                or candidate.suffix.casefold() in SENSITIVE_PACKAGE_SUFFIXES
            ):
                raise CommandFailure(f"Refusing sensitive package file: {relative}")
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except (OSError, ValueError) as error:
                raise CommandFailure(f"Package file escapes project: {relative}") from error
            mode = resolved.stat().st_mode
            if not stat.S_ISREG(mode):
                raise CommandFailure(f"Refusing non-regular package input: {relative}")
            yield relative, resolved


def _package_directory_allowed(relative: Path) -> bool:
    return any(
        relative == included or relative in included.parents or included in relative.parents
        for included in PACKAGE_DIRECTORIES
    )


def _package_file_allowed(relative: Path) -> bool:
    if len(relative.parts) == 1:
        return relative.name in PACKAGE_ROOT_FILES
    return any(included in relative.parents for included in PACKAGE_DIRECTORIES)


def _write_package_archive(root: Path, archive: Path, *, excluded: set[str]) -> None:
    """Write a deterministic archive from validated repository-local files."""

    if archive.is_symlink():
        raise CommandFailure(f"Refusing symlinked package archive: {archive}")
    temporary = archive.with_name(f".{archive.name}.tmp-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for relative, path in _iter_package_files(root, archive=archive, excluded=excluded):
                info = zipfile.ZipInfo(relative.as_posix(), (2026, 9, 2, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
                bundle.writestr(info, path.read_bytes())
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "doctor": command_doctor,
        "setup": command_setup,
        "dev": command_dev,
        "serve": command_serve,
        "strictdoc-serve": command_strictdoc_serve,
        "validate": command_validate,
        "index-capella": command_index_capella,
        "export": command_export,
        "test": command_test,
        "build": command_build,
        "clean": command_clean,
        "package": command_package,
    }
    for name, handler in handlers.items():
        command = subparsers.add_parser(name)
        command.set_defaults(handler=handler)
        if name == "test":
            command.add_argument("--no-e2e", action="store_true")
        elif name == "export":
            command.add_argument(
                "--formats",
                nargs="+",
                choices=("html", "pdf", "excel", "json", "reqif"),
            )
        elif name == "package":
            command.add_argument("--skip-checks", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (CommandFailure, OSError, ValueError, importlib.metadata.PackageNotFoundError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
