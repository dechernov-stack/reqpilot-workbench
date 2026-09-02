# Stage gates

Commands are executed with the Python runtime resolved from `uv.lock`. On this
host, a mirror under `/private/tmp` is used during development because macOS
File Provider may evict large executable files inside the workspace.

## Stage 0 — compatibility spikes

Status: **PASS**, with real Capella checks explicitly not executed.

| Gate | Result | Evidence |
|---|---|---|
| StrictDoc validation/export | PASS | Native JSON export of 5 documents, 24 requirements and 27 relations |
| Safe write/rollback spike | PASS | Native writer round-trip, invalid pre-commit rejection and injected post-`os.replace` backup restore; canonical manifest unchanged |
| Python checks | PASS | Ruff, format check and `py_compile` for both spike scripts |
| capellambse handshake | PASS | Exact 0.8.0 under isolated Python 3.12 runtime |
| Real Capella load/SVG/hash | NOT EXECUTED | No GUI or legally usable real model was available |
| Backend tests | NOT AVAILABLE | Backend application is intentionally created in Stage 1 |
| Frontend tests/build | NOT AVAILABLE | Frontend application is intentionally created after Stage 0 |

Reproduction:

```text
.venv/bin/python tools/spike_strictdoc.py
.venv-capella/bin/python tools/spike_capella.py
.venv/bin/strictdoc export requirements --config requirements/strictdoc_config.py \
  --output-dir tmp/spikes/json-baseline --formats=json --no-parallelization
```

## Stage 1 — repository and application skeleton

Status: **PASS**.

- locked Python and Node dependency graphs are present;
- FastAPI, React/Vite, CI and the cross-platform `tools/reqpilot.py` command
  interface are implemented;
- the exact `dev` command starts Uvicorn and Vite using the validated backend
  port and proxy target; both endpoints and `/api/health` were probed;
- the production frontend is served by FastAPI on `127.0.0.1` without
  unrestricted CORS;
- validate, backend tests, frontend tests and production build passed after the
  stage.

## Stage 2 — StrictDoc integration

Status: **PASS**.

- 5 canonical `.sdoc` documents contain 24 requirements and 27 internal
  relations;
- native read/write, safe CRUD, UID/MID validation, optimistic concurrency,
  rollback and deleted-UID protection pass;
- native HTML, PDF, Excel, JSON and ReqIF exports pass;
- validate, backend tests, frontend tests and production build passed after the
  stage.

## Stage 3 — Capella adapter

Status: **PASS for fixture automation; REAL CAPELLA TEST: NOT EXECUTED**.

- exact capellambse 0.8.0 worker handshake passes;
- fixture indexing returns 37 elements, 41 relations and 3 labelled SVGs;
- live-mode configuration, process isolation and read-only boundaries are
  implemented;
- no legal real model or Capella GUI was available, so real UUID/SVG/hash checks
  were not executed;
- validate, backend tests, frontend tests and production build passed after the
  stage.

## Stage 4 — cross-tool trace links

Status: **PASS**.

- 10 schema-versioned YAML links use requirement MID/UID and architecture UUID;
- CRUD, validation, rename-by-UUID stability and broken-link diagnostics pass;
- path/symlink confinement, lock, backup and compare-and-swap checks pass;
- validate, backend tests, frontend tests and production build passed after the
  stage.

## Stage 5 — analytics

Status: **PASS**.

- unified graph traversal/filtering and cycle protection pass;
- requirement→test, requirement→function, requirement→component and
  function→component matrices pass;
- impact direction, depth and explainable paths pass;
- dashboard and autonomous combined HTML generation pass;
- validate, backend tests, frontend tests and production build passed after the
  stage.

## Stage 6 — user interface

Status: **PASS**.

- dashboard, requirements, architecture, traceability/graph, matrices, impact,
  exports and diagnostics screens are implemented in Russian;
- fixture banner, loading/error/empty states, CRUD conflicts and CSV/download
  paths are covered;
- five real browser screenshots are 1280×720 PNG files, and the three-pane
  requirements/architecture layouts fit the specified 1280 px working width;
- 27 Vitest tests pass with 87.77% coverage;
- one isolated Playwright fixture scenario passes;
- validate, backend tests, frontend tests and production build passed after the
  stage.

## Stage 7 — consolidated release gate

Status: **PASS for automated scope; manual real-Capella scope NOT EXECUTED**.

| Final gate | Result | Evidence |
|---|---|---|
| `doctor` | PASS | No blocking problem; missing Capella GUI is an explicit warning |
| `validate` | PASS | 24 requirements, 24 unique UIDs, 24 unique MIDs |
| Backend | PASS | 124 passed, 1 skipped, 87.50% coverage |
| Ruff | PASS | Format and lint checks |
| mypy | PASS | Strict check over 34 backend source files |
| Frontend | PASS | 27 passed, 87.77% coverage |
| Playwright | PASS | 1 fixture E2E passed in a disposable project |
| Prettier / ESLint | PASS | Formatting and zero-warning lint |
| npm audit | PASS | 0 known vulnerabilities |
| Production build | PASS | TypeScript and Vite bundle |
| ReqIF verifier | PASS | 5 specifications, 24 hierarchy nodes, 24 objects, 27 relations, 0 unresolved references |
| Native outputs | PASS | HTML, PDF, five XLSX workbooks, JSON, ReqIF and combined HTML |
| Real Capella | NOT EXECUTED | No GUI or legally usable real model |

Only the final consolidated coverage XML and curated export manifest are kept
as machine-readable repository evidence; intermediate console logs are not
presented as stronger evidence than the final run. A skipped real-Capella check
is never converted to a fixture PASS.
