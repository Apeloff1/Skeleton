# Queue operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `pending_pressure` | Pending backlog relative to admission capacity | `pending_jobs,queue_limit` |
| `oldest_wait_ms` | Age of oldest queue member | `observation_ns,oldest_created_ns` |
| `running_occupancy` | Observed concurrently running job fraction | `running_jobs,running_limit` |
| `max_wait_ratio` | Backlog age relative to service-level expectation | `oldest_wait_ms,service_level_ms` |
| `per_tenant_share` | Concurrent worker share for a tenant | `tenant_running,all_running` |
| `throughput_per_sec` | Completed tasks per elapsed second | `completed_jobs,elapsed_seconds` |
| `completion_ratio` | Share of submitted jobs with committed completion | `completed_jobs,submitted_jobs` |
| `held_ratio` | Explicitly held jobs relative to accepted work | `held_jobs,submitted_jobs` |
| `retry_suppression_ratio` | Uncertain outcomes protected from blind retry | `suppressed_retries,uncertain_outcomes` |
| `admission_rejection_rate` | Capacity or contract rejection fraction | `rejected_requests,total_requests` |
| `queue_turnover` | Backlog turnover over measured window | `completed_jobs,mean_pending_jobs` |
| `worker_idle_ratio` | Share of observed worker time without inference | `idle_ms,total_worker_ms` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue`
and call `measure()` with exactly the required numeric counters. An unexpected,
missing, nonfinite, Boolean, negative, or oversized value is rejected.

Counters need independent source custody: production deployments should derive
inputs from the authoritative SQLite spine, Linux kernel observations,
operator-authorized model metadata, or separately executed evaluation data.
These computations do not verify their own external inputs and are **not**
release evidence unless the input collection is independently attested.

## Regression guarantees

Each contract is covered by independent exact-oracle, deterministic fingerprint,
missing-field, unexpected-field, Boolean, negative, nonfinite, oversized,
zero-denominator and wrong-input-type regression tests. They are run only
after the implementation is complete. Never interpret a skipped real-model
test as a passing result.

## Integration

The domain registry exposes a closed set of names. The `measure()` function
can support a future readiness report but must remain observational. For
release admission, consult authoritative final-head workflow checks and
real checkpoint/hardware qualification rather than these scores.
