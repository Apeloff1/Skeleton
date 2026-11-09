# Provider stream reliability

Issue #123 requires explicit provider failure injection and streaming load evidence. The canonical `ModelRuntime.stream_chat()` path now applies the same bounded `RetryPolicy` concept used by non-streaming model calls, with a stricter rule for output integrity.

## Retry contract

A transient provider failure may be retried only while the stream has emitted **zero events**. Once any text/tool/completion event has crossed the runtime boundary, a later transient failure is propagated immediately and the provider is not restarted. Restarting after partial output could duplicate tokens or tool-call deltas and is therefore fail-closed.

The stream retry budget also shares one total timeout deadline across all attempts and retry backoff. Cancellation and timeout errors are never converted into transient retries.

For non-streaming fallback, the same `RetryPolicy` is forwarded into `ModelRuntime.chat()`.

## Concurrent recovery profile

Run deterministic streaming pressure without a network/provider dependency:

```bash
python -m skeleton.testing.provider_stream_reliability_profiles \
  --runs 250 \
  --concurrency 16 \
  --chunks 4 \
  --transient-failures 2 \
  --max-attempts 3 \
  --json
```

A healthy recovery result has:

- `completed == runs`
- `failed == 0`
- `total_provider_attempts == runs * 3`
- `max_provider_attempts == 3`
- `total_events == runs * 5` (four text chunks plus one completed event)
- `invariants_passed == true`

The profile reports p50 time-to-first-event plus p95/max completion latency for comparable-environment baselines. CI gates structural invariants rather than machine-specific timing thresholds.

## Retry-exhaustion profile

Inject more failures than the retry budget:

```bash
python -m skeleton.testing.provider_stream_reliability_profiles \
  --runs 250 \
  --concurrency 16 \
  --chunks 4 \
  --transient-failures 5 \
  --max-attempts 2 \
  --json
```

A healthy exhaustion result has every run fail with exactly two provider attempts and zero emitted events. This proves provider outage pressure cannot produce unbounded stream restart loops.

## Canonical regression pressure

The required quality gate executes focused regressions that assert:

- pre-emission transient failures recover at the configured attempt budget;
- post-emission transient failures are never replayed;
- retry exhaustion performs exactly the configured number of provider attempts;
- retry backoff consumes the same total stream deadline rather than resetting it;
- 32 concurrent recovery streams with two injected failures each complete with exactly 96 provider attempts and 128 events;
- 24 concurrent exhaustion streams fail closed with exactly 48 attempts and zero events.

This slice advances #123's streaming-load and explicit provider-failure coverage. Storage failure injection, broader process-level resource soak, and representative environment capacity baselines remain separate work.