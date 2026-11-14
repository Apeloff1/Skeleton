# Storage lazy-loader inventory repair — 2026-11-13

## Source and failure

The new \`backend/core/telemetry_privacy.py\` is importable, but
\`backend/core/lazy_registry.py\`'s reviewed literal \`_LOADERS\` table
omitted \`core.telemetry_privacy\`. In PR #5296's exact-head mainline
replay job 132061618553 (run 43476509166), this caused two distinct
observed failures:

- \`test_literal_loader_inventory_matches_declared_repository_modules\`
  failed because the core module inventory included telemetry_privacy
  while the allowlist did not.
- \`POST /api/storage/lazy/wrap\` returned 500 because \`wrap_all\`
  attempted to construct a proxy for a known module without a reviewed
  literal loader; the public error boundary correctly redacted it.

## Repair

Register \`core.telemetry_privacy\` with an explicit lambda literal
\`importlib.import_module('core.telemetry_privacy')\`, preserving the
existing no-user-selected-import security invariant. Do not change
\`lazy_import\` to accept arbitrary names or weaken inventory tests.

Add regressions for no eager import, correct literal target and
full public storage wrapping with the module registered.

## Exact-head qualification

\`PYTHONPATH=.:backend python -m pytest -q --noconftest
backend/tests/test_storage_lazy_registry.py\`

Also run \`python backend/scripts/check_dynamic_import_safety.py\`
(or the canonical repository command as defined in CI), then exact
Backend Quality and Merge Readiness checks. No merge/release until
exact-head evidence qualifies.

This repairs an existing baseline/mainline regression but does not
claim that historic game-builder recovery is fully qualified.
