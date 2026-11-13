# Security operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `signed_grant_fraction` | Privileged actions with independent signed permission | `signed_actions,privileged_actions` |
| `deny_rate` | Policy-denied action fraction | `denied_actions,attempted_actions` |
| `tools_by_scope` | Tool exposure per independently authorized scope | `enabled_tools,authorized_scopes` |
| `replay_rejection_fraction` | Repeated invocations refused by replay fencing | `replayed_denials,repeated_requests` |
| `lease_expiry_margin` | Time to authority expiry at observation | `expires_ns,observed_ns` |
| `unauthorized_attempt_ratio` | Unauthorized attempts relative to all invocations | `unauthorized_attempts,total_attempts` |
| `checksum_failure_rate` | Content-addressed custody violations | `digest_mismatches,checked_artifacts` |
| `permission_scope_density` | Granted operation share of possible actions | `granted_actions,available_actions` |
| `approval_age` | Age of independent operator permission | `now_ns,approved_ns` |
| `leakage_prevention_rate` | Prevented detected exposure fraction | `blocked_exposures,detected_exposures` |
| `revoked_source_fraction` | Share of knowledge sources revoked | `revoked_sources,approved_sources` |
| `path_guard_rejections` | Rejected unsafe filesystem entries | `unsafe_paths,inspected_paths` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security`
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
