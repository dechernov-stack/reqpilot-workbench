# Pump Station Capella model blueprint

This is the exact blueprint for the real model to be created manually in
Eclipse Capella 7.1.0. It is documentation, not a fabricated `.capella` or
`.aird` file and not evidence of a live integration.

## Operational Analysis

Actors:

- `Operator`;
- `Maintenance Engineer`.

Capabilities:

- `Monitor Pump Station`;
- `Respond to Pressure Alarm`;
- `Review Event History`.

## System Analysis

System:

- `Pump Station Monitoring System`.

External actors:

- `Sensor Gateway`;
- `Pump Controller`;
- `Operator`.

Functions:

- `Acquire Telemetry`;
- `Validate Measurements`;
- `Determine Pump State`;
- `Evaluate Pressure Threshold`;
- `Manage Alarm Lifecycle`;
- `Store Event`;
- `Publish HMI State`.

Functional exchanges:

- `Raw Telemetry`;
- `Validated Measurement`;
- `Pump State`;
- `Alarm Event`;
- `Acknowledgement`;
- `Event Record`;
- `HMI Update`.

Functional chain:

- `Pressure Alarm Handling`.

## Logical Architecture

Components:

- `Telemetry Adapter`;
- `State Processor`;
- `Alarm Manager`;
- `Event Store`;
- `HMI Service`.

Allocate the corresponding System Functions to these components and model the
exchanges required by the System Analysis.

## Initial cross-tool links

Use real Capella UUIDs in `trace-links.yaml`; the following names are only
human-readable snapshots.

| Requirement | Architecture element |
|---|---|
| `STK-001` | `Monitor Pump Station` |
| `STK-002` | `Respond to Pressure Alarm` |
| `SYS-001` | `Publish HMI State` |
| `SYS-002` | `Evaluate Pressure Threshold` |
| `SYS-003` | `Manage Alarm Lifecycle` |
| `SYS-004` | `Store Event` |
| `IF-001` | `Raw Telemetry` |
| `SW-003` | `Alarm Manager` |
| `SAF-001` | `Validate Measurements` |
| `SAF-002` | `Pressure Alarm Handling` |

## Required representations

Create and save at least three real diagrams in the `.aird` representation:

1. an Operational Analysis view with actors and capabilities;
2. a System Analysis view or functional-chain view for
   `Pressure Alarm Handling`;
3. a Logical Architecture view with components and allocations.

ReqPilot resolves elements and diagrams by their real Capella UUID. Renaming a
model element must therefore preserve a valid link, while deleting its UUID
must produce a broken-link diagnostic.
