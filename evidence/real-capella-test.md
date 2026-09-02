# Real Capella evidence

**REAL CAPELLA TEST: NOT EXECUTED**

As of 2026-09-02 the host has no Eclipse Capella 7.1.0 installation, Java
runtime, Requirements Viewpoint 0.14.0, or legally usable real Capella model.

Consequently these checks were not executed:

- live model load and UUID resolution;
- real diagram enumeration and SVG rendering;
- before/after SHA-256 comparison of model files;
- ReqIF import into Requirements Viewpoint;
- real `.bridgetraces` creation;
- second ReqIF Diff/Merge.

The fixture adapter is tested separately and is not accepted as evidence for
any item above. See `capella/ACCEPTANCE_CHECKLIST.md` for the manual procedure.
