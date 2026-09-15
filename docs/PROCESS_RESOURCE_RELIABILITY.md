# Process resource reliability

Issue #123 requires broader process-level soak evidence in addition to the existing path-specific state, retrieval, API, and provider reliability profiles.

`run_process_resource_soak_profile()` repeatedly exercises the real in-process `APIGateway` dispatch path after warmup while measuring resources owned by the current Python process. It intentionally avoids cache, rate limiting, network calls, and external providers so retained resources can be attributed to request bookkeeping rather than external systems.

## Measured resources

The profile records:

- completed/failed requests and exact route call/error accounting;
- rate-limit bucket cardinality before and after the soak;
- active process thread count before and after the soak, plus the count of newly retained threads;
- open file-descriptor count on Linux via `/proc/self/fd` when available;
- `tracemalloc` current and peak bytes;
- retained allocations attributed directly to `skeleton/api/gateway.py` before and after the soak;
- wall-clock duration and requests/second as informational capacity telemetry.

The canonical regression allows at most 64 KiB of additional retained allocation attributed to `gateway.py` after warmup and garbage collection. This is intentionally a retained-source bound rather than a whole-process RSS threshold: pytest, import caches, allocators, and shared CI runners can change process RSS for reasons unrelated to the gateway under test.

No new thread may remain after the soak. On Linux, the post-soak file-descriptor count may not exceed the pre-soak count. Resources that disappear during the measurement are allowed, which avoids treating unrelated suite cleanup as a leak. The unlimited route must also retain zero rate-limit buckets, and all request/route accounting must remain exact.

## Run locally

For a larger local soak:

```bash
python -m skeleton.testing.process_resource_reliability_profiles \
  --iterations 20000 \
  --warmup 256 \
  --json
```

The canonical quality gate runs a smaller deterministic regression of 2,048 measured requests after 128 warmup requests.

## GitHub-hosted capacity capture

`.github/workflows/reliability-capacity-baseline.yml` provides one pinned execution class for future comparisons: GitHub-hosted `ubuntu-latest` with Python 3.11.16. It runs three larger deterministic profiles and writes their verbatim JSON into the workflow step summary:

- API gateway: 5,000 requests at concurrency 32;
- provider streaming: 250 runs at concurrency 16, four chunks, two injected transient failures, three-attempt budget;
- process resources: 20,000 measured gateway requests after 256 warmup requests.

The workflow runs when its profile/workflow inputs change and can also be dispatched manually. A baseline record is not considered established until the completed workflow's commit SHA, execution class, and verbatim JSON results are copied into the reliability documentation. This keeps measured values separate from guessed or machine-independent thresholds.

## Interpreting results

`requests_per_second`, `elapsed_ms`, and whole-process traced memory are telemetry, not universal pass/fail thresholds. Compare those numbers only on equivalent runtime and hardware classes. Structural invariants and retained gateway-source growth are the portable correctness gates.

This profile provides the process-level soak evidence missing from #123. The remaining acceptance work is to record the first completed representative-environment capacity run produced by the hosted workflow.
