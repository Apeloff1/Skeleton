# Transport operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `request_success_rate` | Authenticated API operations completed successfully | `successful_http,total_http` |
| `unauthorized_requests` | Rejected unauthorized HTTP traffic | `unauthorized_http,total_http` |
| `frame_bytes_ratio` | Native IPC frame use against admitted ceiling | `frame_bytes,max_frame_bytes` |
| `connection_occupancy` | Concurrent loopback connection utilization | `active_connections,max_connections` |
| `stream_lag` | Undelivered durable event count | `latest_event_sequence,delivered_sequence` |
| `cursor_age` | Event cursor staleness in positions | `latest_sequence,client_sequence` |
| `event_delivery_rate` | Events delivered to downstream local clients | `delivered_events,elapsed_seconds` |
| `duplicate_delivery_ratio` | Idempotent repeated delivery proportion | `duplicate_deliveries,delivered_events` |
| `throttle_fraction` | Admission throttles imposed on API traffic | `throttled_http,total_http` |
| `disconnect_rate` | Client disconnect fraction | `client_disconnects,client_connections` |
| `heartbeat_age` | Age of verified worker heartbeat | `now_ns,last_heartbeat_ns` |
| `client_poll_ratio` | Polling operations as share of client requests | `poll_requests,client_requests` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport`
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
