# Deployment operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `install_complete_fraction` | Installed model shard completion fraction | `installed_shards,required_shards` |
| `missing_shard_fraction` | Required model assets absent from installation | `missing_shards,required_shards` |
| `verified_bytes_ratio` | Verified model-byte fraction at activation | `verified_bytes,model_bytes` |
| `daemon_uptime` | Observed daemon lifetime in seconds | `now_ns,started_ns` |
| `restart_success_ratio` | Successful bounded restart fraction | `successful_restarts,attempted_restarts` |
| `memory_pressure_ratio` | Memory reservations relative to measured headroom | `reserved_bytes,available_bytes` |
| `startup_held_ratio` | Startup attempts rejected by custody gates | `held_starts,total_starts` |
| `manifest_completeness` | Model manifest completeness under schema | `validated_fields,required_fields` |
| `health_probe_success_ratio` | Responsive, identity-bound liveness proofs | `healthy_probes,all_probes` |
| `canary_pass_rate` | Independent real-model canary acceptance fraction | `passed_canaries,executed_canaries` |
| `device_coverage` | Device configurations tested successfully | `qualified_devices,target_devices` |
| `native_e2e_coverage` | Approved real-model end-to-end coverage | `completed_native_flows,planned_native_flows` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment`
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
