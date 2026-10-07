# Durable State Storage Chaos Profile

This profile closes the explicit durable-storage failure-injection gap tracked by reliability issue #123 without depending on external services or machine-specific timing.

## Fault model

`run_state_storage_failure_recovery_profile()` uses the real `SQLiteRunStore` with a test-only connection fault injector. The injector rejects exactly the next SQLite connection attempt with `sqlite3.OperationalError("injected storage unavailable")`, modeling a temporarily unavailable durable-storage boundary before a transaction begins.

The profile injects one outage at each write stage of a complete durable lifecycle:

1. run claim;
2. step start;
3. step completion;
4. checkpoint creation;
5. terminal run transition.

Each interrupted operation is retried once with the same semantic identity and expected revision.

## Required invariants

A healthy run must prove all of the following:

- all five injected outages are observed;
- all five retries succeed;
- exactly one run row exists;
- exactly one step row exists;
- exactly one checkpoint row exists;
- the checkpoint revision is exactly `1`;
- the terminal run revision is exactly `2` (`claim` + terminal transition only);
- resume after the checkpoint has zero replay steps;
- the terminal run is not reported as recoverable;
- the final status is `succeeded`.

These invariants make accidental duplicate durable writes or double revision advancement visible even when the retry ultimately succeeds.

## Run locally

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_state_reliability_profiles.py
```

The canonical quality gate already executes this test file, so the storage-chaos regression is exercised anywhere `scripts/quality-gates.sh` is authoritative.

## Scope and remaining reliability work

This is deterministic connection-boundary chaos, not a filesystem corruption or mid-commit power-loss simulator. It verifies atomic behavior and clean retry recovery when durable storage is temporarily unavailable. Issue #123 still needs representative-environment capacity numbers, streaming pressure coverage, and broader process-level memory/resource soak evidence before the repository-wide reliability program is complete.
