# Tooling operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `accepted_call_ratio` | Approved invocations versus model proposals | `accepted_calls,tool_requests` |
| `effect_ambiguity_ratio` | Uncertain effects held instead of replayed | `ambiguous_effects,started_effects` |
| `approval_consumption_fraction` | One-time authority redemption fraction | `redeemed_grants,issued_grants` |
| `budget_utilization` | Consumed externally authorized tool budget | `consumed_tool_budget,allowed_tool_budget` |
| `execution_latency` | Average observed tool execution latency | `total_tool_ms,completed_tools` |
| `sandbox_denial_ratio` | Blocked resource escapes among attempts | `sandbox_denials,tool_attempts` |
| `side_effect_rate` | Ratio of tool calls with external effects | `side_effect_operations,completed_tools` |
| `explicit_denial_fraction` | Operator refusals to requested permissions | `refused_grants,requested_grants` |
| `timeout_fraction` | Tool invocations exceeding their deadlines | `timed_out_tools,started_tools` |
| `tool_result_size_ratio` | Tool output pressure against bounded response size | `result_bytes,result_limit_bytes` |
| `idempotent_reply_fraction` | Receipts returned without repeating external effects | `replayed_receipts,total_tool_receipts` |
| `human_review_ratio` | Privileged tool actions receiving human review | `reviewed_tool_actions,privileged_tool_actions` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling`
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
