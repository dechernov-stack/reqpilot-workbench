# Capella Stage 0 spike

Generated: `2026-09-02T09:30:40.643620+00:00`

**REAL CAPELLA TEST: NOT EXECUTED**

This spike never uses fixture data as evidence for a real Capella run. It does not invoke `save()` or launch the Capella GUI.

| Check | Result | Evidence |
|---|---|---|
| capellambse runtime | PASS | distribution/module: 0.8.0 / 0.8.0; expected: 0.8.0 |
| Capella GUI | NOT FOUND | Not found in PATH, CAPELLA_HOME, /Applications, or ~/Applications |
| Real model configuration | NOT CONFIGURED | mode=fixture; model_path=None |
| UUID indexing and lookup | NOT EXECUTED | No configured real model was opened |
| In-memory SVG rendering | NOT EXECUTED | No configured real model was opened |
| SHA-256 proof | NOT EXECUTED | No configured real model was opened |

## Current outcome

Fixture mode is not evidence of a real Capella model

No Capella GUI or legally usable real model was supplied to this repository, so model loading, UUID verification, diagram enumeration, SVG rendering, and the before/after model hash comparison remain **NOT EXECUTED**. This is an environment boundary, not a fixture pass.


## Reproduction

```text
.venv-capella/bin/python tools/spike_capella.py
```

To perform the real spike later, set `capella.mode: live`, `capella.model_path`, `capella.entrypoint` when the path is a directory, and keep `capella.read_only: true`; then rerun the same command with the isolated `.venv-capella` interpreter.

## Machine-readable result

```json
{
  "capella_gui_candidates": [],
  "capella_mode": "fixture",
  "capellambse_distribution_version": "0.8.0",
  "capellambse_expected_version": "0.8.0",
  "capellambse_module_version": "0.8.0",
  "capellambse_version_exact": true,
  "config_path": "/Users/dmitriychernov/Documents/Codex/2026-09-01/files-mentioned-by-the-user-tz/outputs/reqpilot-workbench/project.yaml",
  "configured_entrypoint": null,
  "configured_model_path": null,
  "configured_read_only": true,
  "expected_capella_gui_version": "7.1.0",
  "fixture_used": false,
  "generated_at": "2026-09-02T09:30:40.643620+00:00",
  "model_inspection": null,
  "python": "3.12.14",
  "real_capella_test": "REAL CAPELLA TEST: NOT EXECUTED",
  "reason": "Fixture mode is not evidence of a real Capella model",
  "status": "NOT EXECUTED"
}
```
