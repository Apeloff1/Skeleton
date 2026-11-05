# Model operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `memory_available_margin` | Available host RAM after observed reservations | `available_bytes,reserved_bytes` |
| `vram_headroom` | Observed accelerator-memory capacity margin | `vram_limit_bytes,vram_used_bytes` |
| `kv_cache_bytes_per_token` | KV allocation per admitted context token | `kv_bytes,context_tokens` |
| `batch_utilization` | Active sequence fraction of worker capacity | `active_sequences,sequence_capacity` |
| `token_budget_left` | Remaining native model context | `context_ceiling,prompt_tokens,output_reserved_tokens` |
| `loader_duplication_bytes` | Worst observed model-memory copy budget | `model_bytes,resident_model_copies` |
| `active_model_ratio` | Active-to-registered model ratio | `active_models,registered_models` |
| `host_reserve_ratio` | Reserved share of available RAM | `reserved_bytes,available_bytes` |
| `shard_integrity_fraction` | Verified model shard fraction | `verified_shards,total_shards` |
| `tokenizer_mismatch_count` | Identity mismatches detected during model operations | `tokenizer_mismatches,active_models` |
| `setup_latency_per_gb` | Model activation latency normalized to size | `setup_ms,model_bytes` |
| `workers_per_model` | Worker multiplicity per loaded model | `active_workers,active_models` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model`
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
