# StrictDoc 0.29.0 compatibility spike

**Result:** PASS  
**Executed:** 2026-09-02  
**Scope:** native JSON read, parser/model/SDWriter mutation, semantic round-trip,
invalid-candidate rejection, injected post-replace rollback, and
source-integrity proof.

## Command

```console
.venv/bin/ruff format --check tools/spike_strictdoc.py
.venv/bin/ruff check tools/spike_strictdoc.py
.venv/bin/python tools/spike_strictdoc.py
```

All three commands exited with code `0`. The spike verified both the installed
package metadata and the native CLI version as exactly `0.29.0`.

The final repeat check used the File Provider-safe Python 3.12 runtime created
from the repository lock file at `/private/tmp/reqpilot-workbench-venv`; its
`python`, `strictdoc`, and `ruff` reported Python `3.12.14`, StrictDoc `0.29.0`,
and Ruff `0.12.5`, respectively.

## Native StrictDoc paths used

- Read: the installed `strictdoc.cli.main:main` console entry point in a child
  Python process, with `export ... --formats=json --no-parallelization`, followed
  by reading StrictDoc's generated `json/index.json`.
- Write: `ProjectConfigLoader`, `TraceabilityIndexBuilder`,
  `SDocDocumentIterator`, `SDocNode.set_field_value`, and `SDWriter.write` from
  StrictDoc 0.29.0.
- Validation: another native JSON export, which parses all documents, builds the
  traceability graph, and runs StrictDoc's grammar, document, and node validators.
- Processes: argument arrays with `subprocess.run(..., shell=False)` only.

StrictDoc 0.29.0 has no separate top-level `validate` command. Therefore its
native export pipeline is the validation gate for this spike; no custom parser,
regular-expression patcher, or ReqIF implementation is used.

## Valid round-trip

The spike copied `requirements/` into a temporary directory and exported a
native JSON baseline. It then found `SYS-002` through StrictDoc's parsed model
and replaced only `RATIONALE` with this exact multiline Unicode value:

```text
Совместимость записи подтверждена: инженерная проверка № 0.
Строка Unicode: насос ⚙, давление Δp, русский текст.
Финальная строка сохраняется без потери данных.
```

The `SDWriter` result was installed with `os.replace` only in a disposable
validation project. A second native JSON export succeeded and an exact semantic
comparison produced these results:

| Check | Result | Evidence |
|---|---:|---|
| Documents | PASS | 5 documents; metadata, resolved grammar, and order unchanged |
| Requirements | PASS | 24 UIDs before and after |
| Stable UID/MID | PASS | complete UID set and every UID-to-MID mapping unchanged |
| Relations | PASS | all 27 native JSON relations unchanged |
| Non-target fields | PASS | 335 values unchanged |
| Unknown-to-ReqPilot grammar fields | PASS | every field other than the selected `RATIONALE` compared without a hard-coded field allowlist |
| Unicode/multiline | PASS | exact value recovered from the second native JSON export |
| Valid candidate SHA-256 | PASS | `87db581607258481b6481a46b9a1f35a96bb441ff1f524050c973e55d1cc7efc` |

## Invalid candidate and rollback

Using the same parsed node and native writer, the spike produced a second
candidate with the grammar-required `UID` field removed. This candidate was
installed only into another disposable project copy. Native export exited with
code `1` and reported:

```text
Semantic error: Node is missing a field that is required by grammar: UID.
```

The pristine temporary source manifest was byte-identical after the rejection.
The real canonical source manifest was also computed before and after the whole
spike and remained byte-identical.

The spike also exercised the failure path after a successful atomic replacement
in a separate temporary project: it backed up the target, installed the valid
candidate with `os.replace`, injected an exception, restored the backup through
a second `os.replace`, ran native StrictDoc validation again, and compared the
complete source manifest. The restored project was byte-identical to its
pre-write state (`post_replace_rollback_restored: true`).

Canonical manifest digest (SHA-256 of the sorted relative-path/hash mapping):

```text
fb5c3e21b58f29390e25e541ddabf8a049e965d641b753fb24733510af391dd6
```

Individual source hashes after the run:

```text
1acdc1fb855f80e40c26eac2e995b854aeeab38c1842597896d9a01b5b32aaa8  requirements/01_stakeholder.sdoc
29d09c0acec8698abe4426dfa4703f64f6daffe3de0322bd293558a7a4390e01  requirements/02_system.sdoc
4b19c401428ea6bc411d2ce718a22e17fd5c1a2229e48d382d07ec04f2685c76  requirements/03_software_interface.sdoc
db24c6bf5b2678f8571fc35cfc5f962bf92900bb91d4de59325e80628bc48909  requirements/04_safety.sdoc
9cc249343f775adbfad6da5ec30610e69a510c8ef869a44991a72b78c6e89dea  requirements/05_tests.sdoc
c0ad5800c5b5a17de592087dbf930b8f026a271a50806b6f6738379ebf43c6de  requirements/assets/custom.css
43d41900a3249c20db1c78c00c387657691dc69d487f01cb96c2de5da872a484  requirements/assets/favicon.svg
2ee52fb9eab206185e3bf5298d35580f47ab622da27b1eefa987328ee4ec925d  requirements/grammar.sgra
85ceb9c8f9d491c60d862a3562c891c8236c376985d5a832b1d5a1bebc287995  requirements/strictdoc_config.py
```

No canonical `.sdoc`, grammar, configuration, or asset file was written by the
spike. Temporary projects and candidate files were deleted automatically when
the process completed.
