# Environment evidence

Recorded on 2026-09-02 before implementation of the application layers.

## Host

- macOS 26.5.2 (25F84), arm64.
- Python 3.12.14: `/opt/homebrew/bin/python3.12`.
- Node.js 24.18.1 and npm 10.9.8.
- Google Chrome 152.0.7977.75.

## Locked Python runtimes

The target versions cannot coexist in one environment because their
`python-datauri` constraints are mutually exclusive:

- StrictDoc 0.29.0 requires `python-datauri < 3`.
- capellambse 0.8.0 requires `python-datauri >= 3.0.2`.

The repository therefore uses one `uv.lock` with declared conflicting extras
and two isolated Python 3.12 environments:

- `.venv`: application, development tools, and `strictdoc==0.29.0`;
- `.venv-capella`: read-only Capella worker and the official
  `capellambse==0.8.0` Git tag pinned to commit
  `2abba5cd8922a306cdb735a9c19bcfefdb74a7e8`.

Observed:

```text
$ .venv/bin/python --version
Python 3.12.14
$ .venv/bin/strictdoc --version
0.29.0
$ .venv-capella/bin/python -c 'import importlib.metadata as m; print(m.version("capellambse"))'
0.8.0
$ shasum -a 256 uv.lock
076cdd253ceb454db8e48360ec8283813d28e9612ffa3b78535aa1569885a1b1
```

## Capella GUI prerequisites

No Eclipse Capella installation, Java runtime, Requirements Viewpoint 0.14.0,
or legally usable real Capella model was found on this host. Automated fixture
tests are allowed, but they are not evidence of a live Capella integration.
The real-GUI/manual stage is therefore expected to remain
`REAL CAPELLA TEST: NOT EXECUTED` unless the environment changes.

## File Provider incident

The first copied StrictDoc seed files were automatically evicted by the macOS
File Provider and acquired the `compressed,dataless` flags. A native StrictDoc
scan then blocked while reading them. The untouched seed directory was moved to
`tmp/requirements-dataless-seed` and all canonical files under
`requirements/` were recreated through repository patches from the hydrated
source. The native JSON export subsequently completed successfully.
