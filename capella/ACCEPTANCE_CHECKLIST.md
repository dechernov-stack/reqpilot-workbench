# Real Capella acceptance checklist

Current status: **REAL CAPELLA TEST: NOT EXECUTED**

Reason: Eclipse Capella, Requirements Viewpoint and a legally usable real model
are not available on the current host.

Fixture data must not be used to mark any item below as passed.

| # | Manual check | Status | Evidence |
|---:|---|---|---|
| 1 | Backend opens the model through capellambse 0.8.0 | NOT EXECUTED | |
| 2 | UI reports live mode | NOT EXECUTED | |
| 3 | Expected model elements and UUIDs are visible | NOT EXECUTED | |
| 4 | At least three real diagrams are available | NOT EXECUTED | |
| 5 | Real diagram SVG is rendered | NOT EXECUTED | |
| 6 | Ten YAML trace links resolve to real UUIDs | NOT EXECUTED | |
| 7 | Links survive application restart | NOT EXECUTED | |
| 8 | Rename keeps the link valid by UUID | NOT EXECUTED | |
| 9 | Deleted UUID produces a broken link | NOT EXECUTED | |
| 10 | Model file SHA-256 values are unchanged after every P0 read | NOT EXECUTED | |
| 11 | StrictDoc ReqIF imports via Requirements Viewpoint 0.14.0 | NOT EXECUTED | |
| 12 | A real `.bridgetraces` is saved by Capella | NOT EXECUTED | |
| 13 | Second ReqIF is processed through Diff/Merge | NOT EXECUTED | |
| 14 | Limitations and exact tool versions are recorded | NOT EXECUTED | |

When the environment becomes available, copy the before/after file manifest,
tool output and real screenshots into `evidence/`. Do not edit this status
without those artifacts.

