# Evaluation operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `accuracy` | Exact correctness fraction for supplied labeled records | `correct,total` |
| `precision` | Precision of independently scored decisions | `true_positive,false_positive` |
| `recall` | Recall of independently scored decisions | `true_positive,false_negative` |
| `specificity` | Specificity against negative controls | `true_negative,false_positive` |
| `f1` | Harmonic precision/recall summary from confusion counts | `true_positive,false_positive,false_negative` |
| `balanced_accuracy` | Balanced classification accuracy | `true_positive,false_negative,true_negative,false_positive` |
| `brier` | Mean squared probability forecast error | `squared_probability_error,predictions` |
| `mean_absolute_error` | Mean absolute error for supplied labels | `absolute_error_sum,predictions` |
| `false_accept_rate` | False acceptance on independent negatives | `false_accepts,negative_cases` |
| `false_reject_rate` | False rejection on independent positives | `false_rejections,positive_cases` |
| `latency_guard` | Runtime responses exceeding a supplied deadline | `latency_violations,total_cases` |
| `regression_delta` | Observed benchmark change from pinned baseline | `current_score,baseline_score` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation`
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
