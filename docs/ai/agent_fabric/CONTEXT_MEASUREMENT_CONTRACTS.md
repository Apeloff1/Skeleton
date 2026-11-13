# Context operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `retained_turns_fraction` | Fraction of durable dialogue represented in the prompt | `retained_turns,full_turns` |
| `dropped_turns` | Durable dialogue turns omitted from active context | `full_turns,retained_turns` |
| `source_bytes_fraction` | Source-material share of actual context | `source_bytes,context_bytes` |
| `context_occupancy` | Prompt token occupancy | `prompt_tokens,context_ceiling` |
| `citation_rate` | Identifiers verified against retrieved evidence | `valid_identifiers,all_identifiers` |
| `prompt_overhead` | Non-dialogue prompt token overhead | `system_tokens,all_prompt_tokens` |
| `model_output_reserve` | Fraction of context reserved for generation | `reserved_output_tokens,context_ceiling` |
| `source_relevance_gap` | Ranked evidence relevance spread | `top_relevance,last_relevance` |
| `available_token_margin` | Remaining admitted context tokens | `context_ceiling,prompt_tokens,output_tokens` |
| `duplicate_source_fraction` | Sources excluded by provenance deduplication | `duplicate_sources,considered_sources` |
| `trusted_source_ratio` | Operator-approved fraction of selected sources | `approved_sources,selected_sources` |
| `context_estimate_divergence` | Estimator discrepancy relative to tokenizer truth | `estimated_tokens,actual_tokens` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context`
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
