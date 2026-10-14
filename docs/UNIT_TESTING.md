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
