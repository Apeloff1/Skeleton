# Learning operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `dataset_coverage` | Operator-approved training or eval data fraction | `approved_samples,required_samples` |
| `validation_holdout_fraction` | Independent validation holdout coverage | `holdout_samples,all_samples` |
| `contamination_score` | Detected overlap between training and evaluation data | `contaminated_examples,test_examples` |
| `update_acceptance_ratio` | Gate-approved runtime model update fraction | `accepted_updates,proposed_updates` |
| `replay_coverage` | Exact replay of pinned evaluation cases | `replayed_tests,reference_tests` |
| `calibration_gap` | Average calibration discrepancy from fixed tests | `calibration_error_sum,evaluation_count` |
| `distribution_shift_rate` | Feature distribution shift against reference bins | `changed_feature_bins,reference_feature_bins` |
| `reward_hacking_alert_rate` | Potential reward-proxy violations per evaluation run | `reward_hacking_alerts,evaluation_runs` |
| `training_data_rights_coverage` | Training examples with explicit source rights | `rights_approved_samples,all_samples` |
| `test_isolation_score` | Independent holdout isolation fraction | `independent_test_cases,total_test_cases` |
| `gradual_promotion_ratio` | Model updates cleared by progressive canaries | `canary_approved_updates,total_updates` |
| `regression_hold_ratio` | Detected regressions held before promotion | `blocked_regressions,detected_regressions` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning`
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
