# Planning operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `completion_fraction` | Completed DAG steps relative to planned work | `complete_steps,total_steps` |
| `critical_path_share` | Longest dependency chain relative to all work | `critical_path_ms,all_estimated_ms` |
| `parallelism_ratio` | Independent runnable work capacity | `runnable_steps,total_steps` |
| `fanout_ratio` | Dependency fanout density in planned graph | `dependency_edges,total_steps` |
| `dependency_density` | Directed acyclic graph connectivity density | `dependency_edges,possible_edges` |
| `unavailable_step_fraction` | Steps held by unresolved dependencies or policy | `held_steps,total_steps` |
| `tool_step_fraction` | Steps requiring independent effect authority | `tool_steps,total_steps` |
| `review_gate_fraction` | Steps requiring independent human review | `review_steps,total_steps` |
| `unassigned_steps` | Planned steps not assigned to worker ownership | `total_steps,assigned_steps` |
| `longest_chain_ratio` | Sequential graph depth relative to total steps | `longest_chain_steps,total_steps` |
| `plan_overrun_ratio` | Consumed execution budget relative to plan | `consumed_budget,planned_budget` |
| `branch_count_density` | Alternative branch count relative to plan size | `alternative_branches,total_steps` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning`
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
