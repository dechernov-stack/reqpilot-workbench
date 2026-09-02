# Known limitations

- StrictDoc create/update commits one canonical `.sdoc` with a durable temporary
  file, `os.replace`, directory `fsync`, backup and in-process rollback. Deletion
  additionally updates `deleted-uids.json`, so it necessarily performs two
  filesystem replacements. An exception is rolled back, but a hard process or
  host crash in the narrow interval between those replacements has no durable
  recovery journal and can leave the document and tombstone registry at
  different transaction points. The backup remains available for manual
  recovery; after an unclean shutdown, run `validate` and inspect backups before
  further edits. This is a residual crash-consistency risk, not a failure seen in
  the completed tests.
- The real Capella and Requirements Viewpoint workflow is not executed on this
  host; live mode remains contingent on a user-supplied legal model.
- Fixture mode is useful for automated and UI verification only and is always
  labelled as demonstration architecture.
- P0 is a loopback-only single-user workbench. Authentication, authorization
  and multi-user collaboration are outside scope.
- Python4Capella write operations, requirement mirroring and
  `.bridgetraces` automation are P1 and are not implemented.
- Git integration is read-only. ReqPilot never commits, resets or checks out
  files automatically.
- Very large projects are filtered server-side before graph rendering; the UI
  intentionally does not render an entire multi-thousand-node graph by
  default.
- Native PDF export requires a locally installed Chrome/Chromium and an
  explicitly configured executable `REQPILOT_CHROMEDRIVER`. ReqPilot does not
  download a driver during normal operation. The default all-format export
  reports PDF as `NOT EXECUTED` and continues when no driver is configured; an
  explicit `export --formats pdf` request fails, and a mismatched configured
  driver also fails. Neither case is hidden.
- The expert-only `package --skip-checks` option intentionally does not refresh
  native exports or curated samples. It accepts only an already gated sample set
  whose manifest revision matches the canonical sources and whose file sizes and
  SHA-256 digests verify. It cannot be used to refresh stale artifacts.
- Poppler 26.01 emits three `name token longer than spec` warnings while
  rendering the 41-page StrictDoc 0.29.0 printable bundle and visibly clips one
  page. Rendering the same PDF with Chrome/PDFium, including that page, is
  complete and legible. The individual PDFs also render correctly; this is
  recorded as a StrictDoc/native post-processing interoperability limitation,
  not silently treated as a clean Poppler pass.
- On this development host, macOS File Provider intermittently evicted
  dependency executables from the workspace. Verification therefore used
  lock-file-derived runtime mirrors under `/private/tmp`. A normal local clone
  outside a provider-managed folder does not require that workaround.
