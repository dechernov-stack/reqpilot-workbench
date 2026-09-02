# Architecture fixture

`architecture-fixture.json` is a deterministic, explicitly labelled test
fixture for local development, unit tests and Playwright. It is not exported
from Eclipse Capella and must never be cited as evidence of a real Capella
7.1.0 integration.

The fixture follows the names in `capella/MODEL_BLUEPRINT.md` and contains:

- 37 elements across OA, SA and LA;
- 41 architectural relations;
- three safe inline SVG diagrams;
- stable UUIDs used by the ten demonstration records in `trace-links.yaml`.

The adapter recalculates the fixture fingerprint from file bytes. UI, API and
combined HTML display the banner **«Демо-архитектура, не загруженная из
Capella»** whenever this source is active.

For a real run, switch `project.yaml` to `capella.mode: live`, supply a legal
repository-local model, replace fixture UUID references with real model UUIDs,
and follow `capella/README_REAL_MODEL.md`. Do not rename or copy this JSON to a
Capella file extension.
