# Real Capella setup

## Required desktop tools

- Eclipse Capella 7.1.0.
- Requirements Viewpoint 0.14.0.
- A legally usable model created from [MODEL_BLUEPRINT.md](MODEL_BLUEPRINT.md).
- Python4Capella 1.4.1 only if the optional P1 queue is evaluated.

## Prepare the model

1. Create the model and representations in Capella; do not copy fixture JSON
   into Capella project files.
2. Save the semantic model and its `.aird` representation.
3. Close Capella before the first SHA-256 read-only proof.
4. Put the model inside this repository. P0 rejects paths that escape the
   project root.
5. Set `capella.mode: live`, `model_path` and, for directory models,
   `entrypoint` in `project.yaml`. Keep `read_only: true`.
6. Replace every fixture architecture reference in `trace-links.yaml` with the
   corresponding real model ID, type, name snapshot and UUID from this model.
   Requirement MID/UID values remain unchanged. Do not copy fixture UUIDs into
   a real-model acceptance run.
7. Run:

   ```text
   .venv-capella/bin/python tools/spike_capella.py
   python tools/reqpilot.py doctor
   python tools/reqpilot.py index-capella
   ```

8. Confirm that the reported file manifest has identical SHA-256 values before
   and after model indexing and SVG rendering.

## ReqIF round trip

1. Generate ReqIF with the native StrictDoc export command through
   `python tools/reqpilot.py export`.
2. In Capella, activate Requirements Viewpoint 0.14.0 for the real model.
3. Import the generated ReqIF into the viewpoint.
4. Save the real model and the created `.bridgetraces` file.
5. Generate a second StrictDoc ReqIF after the approved requirement change.
6. Use Capella Diff/Merge according to the viewpoint documentation and record
   the result in `evidence/real-capella-test.md`.

The web backend never invokes Capella GUI and never writes Capella model files
in P0.
