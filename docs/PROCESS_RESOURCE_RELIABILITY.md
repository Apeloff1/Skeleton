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

### Established baseline — 2026-09-15

The first representative hosted baseline completed successfully in **Reliability Capacity Baseline** run `35023566880` (run #5), job `Capture ubuntu-latest capacity baseline`.

Execution record:

- workflow head SHA: `8db441a65a3b09bdc4f0b669d3ef30db721e6709`;
- pull-request merge checkout SHA: `7987b554d89982db2b4a549d18df63d86a45d20b`;
- execution class: GitHub-hosted `ubuntu-latest`;
- runner OS/image: Ubuntu 24.04.5 LTS / `ubuntu-24.04` image `20260907.300.1`;
- machine: x86_64 Linux, 4 CPUs;
- Python: CPython 3.11.16.

Verbatim profile JSON from the successful job:

```json
{"body_mismatches": 0, "completed": 5000, "concurrency": 32, "cpu_count": 4, "failed": 0, "invariants_passed": true, "machine": "x86_64", "max_ms": 0.137, "p50_ms": 0.001, "p95_ms": 0.003, "platform_system": "Linux", "python_implementation": "CPython", "python_version": "3.11.16", "requests": 5000, "requests_per_second": 49819.921, "route_calls": 5000, "route_errors": 0, "wall_ms": 100.361}
```

```json
{"chunks_per_run": 4, "completed": 250, "concurrency": 16, "failed": 0, "invariants_passed": true, "max_completion_ms": 1.971, "max_provider_attempts": 3, "p50_first_event_ms": 0.63, "p95_completion_ms": 1.791, "runs": 250, "total_events": 1250, "total_provider_attempts": 750}
```

```json
{"completed": 20000, "elapsed_ms": 1466.984, "failed": 0, "file_descriptor_delta": 0, "file_descriptors_after": 6, "file_descriptors_before": 6, "gateway_source_after_bytes": 184, "gateway_source_before_bytes": 152, "gateway_source_growth_bytes": 32, "invariants_passed": true, "iterations": 20000, "leaked_threads": 0, "rate_limit_buckets_after": 0, "rate_limit_buckets_before": 0, "requests_per_second": 13633.416, "route_calls": 20256, "route_errors": 0, "thread_delta": 0, "threads_after": 1, "threads_before": 1, "traced_current_after_bytes": 1576, "traced_current_before_bytes": 152, "traced_current_growth_bytes": 1424, "traced_peak_bytes": 3742, "warmup_requests": 256}
```

All three profiles reported `invariants_passed: true`. The process-resource profile completed with zero failed requests, zero leaked threads, zero file-descriptor growth, zero retained rate-limit buckets, zero route errors, and 32 bytes of retained allocation growth attributed to `gateway.py`, well below the 64 KiB regression bound.

## Interpreting results

`requests_per_second`, `elapsed_ms`, and whole-process traced memory are telemetry, not universal pass/fail thresholds. Compare those numbers only on equivalent runtime and hardware classes. Structural invariants and retained gateway-source growth are the portable correctness gates.

The representative baseline required by #123 is now established and recorded above. Future capacity comparisons should preserve the execution class and profile parameters or explicitly document why they differ.
