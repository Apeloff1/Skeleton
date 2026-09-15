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

## Durable state pressure, soak, and storage chaos

`skeleton/testing/state_reliability_profiles.py` exercises the real `SQLiteRunStore` instead of an in-memory fake. The required regression baseline is:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_state_reliability_profiles.py
```

The state suite covers deterministic pressure and failure modes:

- **Concurrent lifecycle pressure:** 24 runs at concurrency 6, each with three durable steps and one checkpoint. Healthy structure is exactly 24 run rows, 72 step rows, 24 checkpoint rows, zero failed runs, and zero recoverable leftovers.
- **Heartbeat soak:** 128 lease renewals on one running record. Healthy structure remains exactly one run row with zero step/checkpoint growth, and the final revision is 130 (claim + 128 heartbeats + terminal transition).
- **Lease-contention chaos:** 12 workers race for one live lease. Exactly one may acquire it; the other 11 must fail with `StateConflict`. After deterministic lease expiry a recovery worker must claim the run and terminate it successfully.
- **Storage-unavailability chaos:** the profile merged in #529 injects one failed SQLite connection at each durable write stage, retries the same semantic operation, and proves exact run/step/checkpoint cardinality plus clean terminal recovery. The full fault model is documented in `docs/RELIABILITY_STORAGE_CHAOS.md`.

The lifecycle and heartbeat helpers also report p50, p95, and maximum operation latency. CI asserts structural correctness rather than machine-dependent latency ceilings. This makes accidental duplicate writes, leaked recoverable runs, or unbounded heartbeat state growth deterministic failures while still preserving timing data for comparable-environment capacity baselines.

## API rate-limit cardinality soak

`tests/test_api_gateway_rate_limit_reliability.py` protects the in-process gateway from retaining rate-limit state for actors that are no longer active. The deterministic soak drives 1,000 unique actor/path keys through a limited route, advances the monotonic clock beyond the one-second limiter window, and then uses unrelated gateway traffic to trigger cleanup.

Healthy structure after expiry is zero retained stale buckets. A companion regression proves the existing two-requests-per-second behavior still returns `429` for the third request inside the active window, then admits traffic again after expiry. Bucket sweeping is throttled to at most once per limiter window so ordinary request handling does not scan the full key map on every call.

The same regression suite also drives 32 callers against one actor/route budget in a thread pool. Exactly eight requests must be admitted and 24 rejected for an eight-request window, proving limiter admission and retained-bucket cardinality stay exact under concurrent callers.

## API gateway concurrent throughput profile

`skeleton/testing/api_gateway_reliability_profiles.py` measures the real in-process `APIGateway` dispatch path with a thread pool. It intentionally disables cache, rate limiting, providers, and network I/O so the result isolates gateway routing, middleware bookkeeping, and shared-state synchronization.

Capture a comparable baseline with:

```bash
python -m skeleton.testing.api_gateway_reliability_profiles \
  --requests 5000 \
  --concurrency 32 \
  --json
```

The JSON result includes:

- completed/failed request counts and body-integrity mismatches;
- route call/error accounting;
- p50, p95, and maximum per-request gateway latency;
- total wall time and requests/second;
- Python version/implementation, operating-system family, machine architecture, and logical CPU count;
- `invariants_passed`, which is true only when every request succeeds with exact response and route accounting.

CI regression coverage uses a smaller 256-request, concurrency-8 profile and gates only on deterministic correctness. Do **not** add a universal requests/second or latency threshold to CI: GitHub-hosted runner hardware varies. For performance regression comparison, record the JSON result together with the commit SHA and runner/execution class, then compare only runs with matching Python/runtime and equivalent hardware class.

A representative capacity baseline should therefore record at minimum:

```text
commit_sha=<tested commit>
execution_class=<runner or host class>
profile=api_gateway_throughput
requests=5000
concurrency=32
<verbatim JSON result>
```

This protocol makes future capacity numbers attributable and comparable without turning noisy shared-runner timing into a correctness gate.

## CI regression baseline

The canonical quality gate runs orchestration, durable-state, and API reliability regressions:

| Scenario | Pressure | Expected structural result |
| --- | --- | --- |
| Orchestration recovery | 32 runs, concurrency 8, 2 transient failures, retry budget 3 | 32 completed, 96 tool attempts |
| Orchestration exhaustion | 24 runs, concurrency 6, 5 transient failures, retry budget 2 | 24 failed, 48 tool attempts |
| State lifecycle | 24 runs, concurrency 6, 3 steps/run | 24 runs, 72 steps, 24 checkpoints, 0 recoverable |
| State heartbeat soak | 128 renewals | 1 run row, 0 steps, 0 checkpoints, revision 130 |
| State lease contention | 12 contenders | 1 live owner, 11 conflicts, successful post-expiry takeover |
| State storage outage | 5 injected connection failures | 5 observed/retried, 1 run, 1 step, 1 checkpoint, terminal revision 2 |
| API limiter cardinality | 1,000 unique actors | 1,000 active buckets during window, 0 stale buckets after expiry |
| API limiter concurrency | 32 callers, shared 8-request budget | 8 admitted, 24 rate-limited, 8 retained timestamps |
| API gateway throughput | 256 requests, concurrency 8 | 256 completed, 0 failed/mismatched, 256 route calls, 0 route errors |

The regression baseline intentionally asserts retry counts, terminal states, durable row cardinality, bounded in-memory state, response integrity, and exact route accounting rather than machine-dependent latency thresholds. Larger performance baselines should be captured on a stable execution class and compared only against equivalent hardware/runtime configuration.

## Remaining #123 coverage

The repository now has repeatable orchestration retry/chaos evidence, durable-state concurrent load/soak/lease recovery, deterministic durable-storage outage recovery, API limiter soak/concurrency invariants, and a repeatable API gateway throughput profile with environment-tagged latency/throughput output. Issue #123 remains open for streaming load, explicit provider-failure injection, broader process-level memory/resource soak evidence, and an actual representative-environment capacity result captured with the protocol above.
