# P0 acceptance report

**Assessed:** 2026-09-02  
**Automated scope:** **PASS**  
**Real Capella manual scope:** **REAL CAPELLA TEST: NOT EXECUTED**

The automated workbench is complete and reproducible in fixture mode. Full P0
acceptance remains conditional on the manual live-Capella checks because this
host had neither Eclipse Capella 7.1.0 with Requirements Viewpoint 0.14.0 nor a
legally usable real model. Fixture evidence is never substituted for those
checks.

## The 24 P0 criteria

| # | Criterion | Test type | Status | Evidence / boundary |
|---:|---|---|---|---|
| 1 | `doctor` has no blocking problem | Automated | PASS | Exact runtime/config/path checks pass; unavailable Capella GUI is an explicit non-blocking warning for fixture mode |
| 2 | `dev`, `validate`, `test`, and `build` succeed | Automated | PASS | Exact `dev` CLI started Uvicorn/Vite and returned health 200; canonical validation, complete test command and production build pass |
| 3 | Requirements are read from `.sdoc` | Automated | PASS | Native StrictDoc JSON normalization loads 5 managed documents and 24 requirements; JSON cache is derivative |
| 4 | CRUD produces valid `.sdoc` | Automated | PASS | Create/update/delete integration tests use StrictDoc model objects and native validation in disposable copies |
| 5 | MID is stable | Automated | PASS | Update/Unicode/relation round-trips preserve all UID-to-MID mappings |
| 6 | Rollback works | Automated | PASS | Invalid candidates never reach canonical files; injected post-replace failure restores byte-identical source |
| 7 | Revision conflict cannot overwrite changes | Automated | PASS | compare-and-swap revision tests and a concurrent two-writer test allow exactly one write and return conflict for the other |
| 8 | StrictDoc opens the changed project | Automated | PASS | Every staged mutation must pass a native StrictDoc 0.29.0 JSON export before commit and is re-read afterward |
| 9 | HTML, Excel, JSON, and ReqIF are generated | Automated | PASS | All four native export jobs succeeded; curated outputs are listed in `exports/samples/manifest.json` |
| 10 | PDF is generated or honestly skipped | Automated + visual QA | PASS | Native PDF job produced a 41-page bundle and five document PDFs using an explicit local ChromeDriver |
| 11 | Fixture mode is visibly identified | Automated | PASS | API source kind/label and permanent Russian UI banner identify demonstration architecture |
| 12 | Live mode reads through capellambse | Automated implementation + manual integration | CONDITIONAL | Isolated worker and exact capellambse 0.8.0 handshake pass; opening a real model is **NOT EXECUTED** |
| 13 | P0 does not change Capella files | Automated policy + manual proof | CONDITIONAL | Code/worker expose read-only operations and never call save; real-model before/after SHA-256 proof is **NOT EXECUTED** |
| 14 | Real SVG diagrams display when available | Manual integration | NOT EXECUTED | Three fixture SVGs pass automated routing/UI tests, but no real `.aird` diagram was available |
| 15 | Cross-tool links are stored in YAML | Automated | PASS | 10 links round-trip through schema-versioned `trace-links.yaml`; MID/UID and Capella UUID are validated |
| 16 | A Capella rename does not break a link | Automated fixture; manual live pending | PASS | Resolution uses UUID rather than `name_snapshot`; fixture rename test passes |
| 17 | Deleted Capella UUID is detected | Automated fixture; manual live pending | PASS | Missing UUID is surfaced as a broken link and included in diagnostics |
| 18 | Unified graph works | Automated | PASS | Backend traversal/filter/cycle tests, frontend graph tests and fixture E2E pass |
| 19 | All four matrices work | Automated | PASS | requirement→test, requirement→function, requirement→component and function→component services/UI/CSV paths pass |
| 20 | Impact analysis shows paths | Automated | PASS | Direction, depth, cycle protection and explainable path tests pass; UI renders the paths |
| 21 | Combined HTML is autonomous | Automated + inspection | PASS | `exports/combined/reqpilot-combined.html` has inline CSS/data and data-URI diagrams, with no external runtime dependency |
| 22 | No fabricated Capella assets are presented as real | Automated + review | PASS | Fixture records/SVGs carry fixture labels; real evidence states the exact NOT EXECUTED outcome |
| 23 | README is reproducible | Automated commands + review | PASS | Locked setup, dual runtimes, commands, PDF driver boundary, fixture/live procedure and outputs are documented |
| 24 | Final report separates automated and manual tests | Review | PASS | This table and `automated-tests.md` distinguish fixture automation from live Capella/Requirements Viewpoint checks |

Summary: **21 criteria pass fully, 2 are conditional on real-model execution
(12 and 13), and 1 is not executed (14).** The conditional/manual status is an
environment boundary, not a test success.

## Requested final status table

| Area | Status | Evidence | Limitation |
|---|---|---|---|
| StrictDoc read | PASS | Native JSON: 5 documents, 24 requirements, 27 relations | None observed in automated scope |
| StrictDoc write | PASS | CRUD and Unicode/multiline native round-trips | Single-user P0; see hard-crash deletion window in known limitations |
| Rollback | PASS | Invalid-candidate rejection and injected exception restore | No durable cross-file transaction journal for an OS/power-loss during deletion |
| Native exports | PASS | HTML, PDF, five XLSX, JSON and ReqIF jobs; combined HTML | PDF needs a matching preinstalled ChromeDriver |
| capellambse fixture | PASS | Exact 0.8.0 handshake; 37 elements, 41 relations, 3 SVGs | Fixture is demonstration data only |
| real Capella read | NOT EXECUTED | `evidence/real-capella-test.md` | GUI and legal model unavailable |
| real diagrams | NOT EXECUTED | `evidence/capella-spike.md` | No real `.aird` was opened |
| trace links | PASS | 10 YAML links, CRUD, resolution and broken diagnostics | Live-model restart/rename/delete remains manual |
| graph | PASS | Backend, frontend and E2E coverage | Large projects are server-filtered |
| matrices | PASS | Four matrix types plus CSV export | Results reflect loaded model/fixture only |
| impact | PASS | Directed traversal with explainable paths | Results reflect currently indexed data |
| Python4Capella P1 | NOT IMPLEMENTED | Explicitly outside P0 | No mirroring, `.bridgetraces` write or automatic Capella save |

## Native data/export checks

- Validation: 24 requirements, 24 unique UID values, 24 unique MID values.
- ReqIF: 5 `SPECIFICATION`, 24 `SPEC-HIERARCHY`, 24 `SPEC-OBJECT`,
  27 `SPEC-RELATION`, 0 unresolved references.
- Fixture: 37 elements, 41 relations, 3 SVG diagrams.
- Tests: backend 124 passed / 1 skipped / 87.50%; frontend 27 passed /
  87.77%; Playwright 1 passed.
- Quality: Ruff, mypy strict, Prettier, ESLint, TypeScript/Vite build and npm
  audit all pass.

## Manual work still required

Follow `capella/ACCEPTANCE_CHECKLIST.md` on a machine with Capella 7.1.0,
Requirements Viewpoint 0.14.0 and a legal model built from
`capella/MODEL_BLUEPRINT.md`. The run must capture real UUID/diagram evidence,
model-file SHA-256 before and after read-only access, ReqIF import,
`.bridgetraces`, and second-import Diff/Merge. Until then:

```text
REAL CAPELLA TEST: NOT EXECUTED
```
