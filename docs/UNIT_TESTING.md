# Feature-scoped Python unit tests

The repository contains Python tests in **three canonical locations**:
`tests/`, `skeleton/testing/`, and `backend/tests/`. The default
`pyproject.toml` testpath is intentionally narrower; use this runner when
you need feature-scoped discovery across all three roots.

Install the development dependencies before running:

```bash
python -m pip install -r requirements-dev.txt
python scripts/run_feature_unit_tests.py --feature jeeves
python scripts/run_feature_unit_tests.py --feature game-builder --feature dragon
python scripts/run_feature_unit_tests.py --feature physics --list
python scripts/run_feature_unit_tests.py --feature security --maxfail 0 --junitxml=unit-results.xml
make test-feature FEATURE=ai
python scripts/run_feature_unit_tests.py --feature provider --collect-only
python scripts/run_feature_unit_tests.py --feature physics --timeout-seconds 300
```

Supported selectors: `ai`, `jeeves`, `game-builder`, `dragon`,
`physics`, `security`, `shell`, `memory`, `agents`, `provider`,
`app`, `backend`, and `all`. Multiple `--feature` arguments select
the union of matching files, sorted and de-duplicated.

The selector matches known file-name tokens and a few explicit test directories.
It excludes files with `e2e`, `integration`, or `live` tokens in their
filenames **or parent directories** unless `--include-integration` is
specified, and does not follow symlinked test files. Other files may still
exercise integrations, so selection is **not** a unit-test or coverage
certification. `--list` previews file selection without importing tests.
`--collect-only` invokes real pytest collection without executing test bodies.

This runner uses pytest with only its explicit asyncio plugin, forwards failures
and collection errors unchanged, fails if no files match, and never falls back
to a different test framework. `--junitxml` emits machine-readable test
results using pytest's built-in output. Existing dedicated `tests/run_unit.py`
and focused CI test lists remain independent and unchanged.

Timeouts return exit code 124; pytest start failures return 126. Exit statuses are never mapped to success. The default timeout is disabled, so use a cap for large or potentially blocking suites.


## Capability alias coverage

Feature selection uses whole underscore-delimited filename tokens, not substring matches. For example, Dragon also selects `webcrawler` modules, game-building includes `forge` and `dialogue`, and application includes `app` and `deployment`. A file may legitimately match several capabilities, but is executed only once per invocation. For multiple requested features, each selector must find at least one file; otherwise the command fails with exit code 2 instead of reporting a misleading successful partial suite.

Symlinks for individual test files and test-root directories are not followed; test paths resolving outside their root are excluded. These guards only validate discovery and do not constitute runtime sandboxing. The feature mapping remains a heuristic rather than an assertion that every test in a capability has been discovered.


## Deterministic test sharding and selection manifests

For large runs, select one-based disjoint partitions. Each test module is assigned
using SHA-256 of its repository-relative POSIX path modulo the total shard count,
so the same repository snapshot and selectors produce the same assignment on
different machines. Sharding is by **test module**, not by individual test case,
and it does not imply equal runtimes or balanced test counts.

```bash
python scripts/run_feature_unit_tests.py --feature ai --shard 1/4
python scripts/run_feature_unit_tests.py --feature ai --shard 2/4
python scripts/run_feature_unit_tests.py --feature ai --shard 3/4
python scripts/run_feature_unit_tests.py --feature ai --shard 4/4
python scripts/run_feature_unit_tests.py --feature ai --shard 1/4 --list-json
```

The `--list-json` output is a stable machine-readable inventory: selection
schema version, requested features, each feature's unsharded test-file count,
integration opt-in, optional shard index and total, the selected relative
paths, and a SHA-256 digest of their compact JSON list. It does not execute
or import tests. To prove execution, use pytest with JUnit output and capture
the commit SHA separately. An empty shard returns error code 2 rather than
reporting a false pass, and every requested feature must be present in the
pre-shard selection.
