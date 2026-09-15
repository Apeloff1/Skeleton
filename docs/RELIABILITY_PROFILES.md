# Reliability profiles

Issue #123 tracks repeatable load, soak, and chaos evidence for critical runtime paths. This document records the in-repository profiles that are safe to run locally and in CI.

## Canonical orchestration retry-pressure profile

Run a deterministic recovery profile with no network or provider dependency:

```bash
python -m skeleton.testing.reliability_profiles \
  --runs 250 \
  --concurrency 16 \
  --transient-failures 2 \
  --max-attempts 3 \
  --json
```

Each run creates an independent canonical orchestrator, driver, tool registry, and flaky tool. The tool fails exactly twice, then succeeds. A healthy result therefore has:

- `completed == runs`
- `failed == 0`
- `total_tool_attempts == runs * 3`
- `max_tool_attempts == 3`
- `invariants_passed == true`

The profile records p50, p95, and maximum wall-clock latency in milliseconds. Timing numbers are environment-specific; compare results only against a baseline captured on comparable hardware and Python/runtime configuration.

## Retry-exhaustion chaos profile

Use more injected failures than the retry budget to verify fail-closed degradation:

```bash
python -m skeleton.testing.reliability_profiles \
  --runs 250 \
  --concurrency 16 \
  --transient-failures 5 \
  --max-attempts 2 \
  --json
```

A healthy exhaustion result has:

- `failed == runs`
- `completed == 0`
- `total_tool_attempts == runs * 2`
- `max_tool_attempts == 2`
- `invariants_passed == true`

This proves that concurrent transient failures cannot create unbounded retry loops. The canonical orchestrator terminates each run at the configured retry budget.

## CI regression baseline

`skeleton/testing/test_orchestration_reliability_profiles.py` pins a small deterministic baseline suitable for the required quality gate:

| Scenario | Runs | Concurrency | Injected failures | Retry budget | Expected result |
| --- | ---: | ---: | ---: | ---: | --- |
| Recovery pressure | 32 | 8 | 2 | 3 | 32 completed, 96 tool attempts |
| Exhaustion pressure | 24 | 6 | 5 | 2 | 24 failed, 48 tool attempts |

The regression baseline intentionally asserts retry counts and terminal states, not machine-dependent latency thresholds. Larger performance baselines should be captured from the CLI profile and compared within the same execution class.

## Remaining #123 coverage

This profile covers canonical orchestration retry pressure and graceful tool-failure degradation. Issue #123 remains open until equivalent repeatable evidence covers API/streaming/state paths, broader soak/resource growth, provider/storage/queue failure injection, and a documented capacity baseline from representative execution environments.
