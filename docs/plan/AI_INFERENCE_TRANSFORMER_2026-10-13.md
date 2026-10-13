# Native inference and transformer implementation — 2026-10-13

Status: implementation candidate. This pass follows the offline workspace work
and targets inference execution and the transformer. The operator explicitly
requested direct implementation without checks or tests. No test, build, lint,
compiler, benchmark, runtime probe or architecture gate was run for this pass.

## Implemented behavior

- Transformer generation returns newly sampled tokens rather than a prefix slice;
  zero requested tokens returns no generated tokens. Device decoding uses the
  same transformer sampling/fallback boundary.
- CPU prefill skips vocabulary projections for intermediate prompt positions.
  Repeated windows reuse their final logits, and matching cached prefixes can
  consume multiple new prompt tokens without discarding prior K/V.
  Uncached CPU inference discards attention probability matrices and backward
  activations between layers. Training retains its backward state.
- CPU backward propagation uses the forward-pass projection weights throughout
  the update, including GELU/SwiGLU and Q/K/V gradients.
- Native cancellation reaches CPU layers/attention rows, Torch layers/configured
  prefill chunks, and waiting accelerator callers. Partially updated caches are
  discarded. Individual numerical kernels and model snapshots remain atomic.
- Cache ownership follows the transformer and training revision. Rotary-only
  single-layer windows honor a smaller admitted context. Accelerator cache reset
  and reserved-byte observations come from the locked execution transition.
- Native generation supports minimum token count, repetition/presence/frequency
  penalties, a bounded penalty window, suppression IDs, string stops and optional
  removal of terminal token text. Request/replay digests bind non-default options.
- Sampling rejects an empty or entirely masked distribution and non-finite
  logits. Centering before temperature division avoids positive overflow;
  zero-probability tokens cannot win a zero-valued random draw.
- Native adapters use declared EOS and stop strings. String-stop streams retain
  token IDs for accounting but buffer visible text until the terminal event.
  Usage includes sampled terminal tokens even when visible text excludes them.
- A completed GenerationStream retains its result on repeated exhaustion.
  Local/service callers close partial streams on failure or cancellation.
- Changes to device/model/tokenizer/limits during generation cannot receive a
  successful mixed-execution receipt. A synchronized accelerator fallback aborts
  that request; a subsequent whole request can use the degraded CPU binding.
- Optional special-token declarations survive transformer snapshots and native
  checkpoint restoration. Checkpoint JSON rejects duplicate keys and non-finite
  constants, and layer activation/normalization must match the declared graph.
- Local inference has configurable concurrency and batch admission limits.
  A failing batch drains sibling workers before returning; cancelled/deadline
  results are not cached, and returned model IDs must match the selected backend.
  Cached tool/structured results own their nested JSON, so caller mutation cannot
  rewrite later cache hits.
  Scheduler cancellation reaches its individual inference task; queue overflow
  rejects admission, and shutdown cannot leave producers behind a sentinel.
- GGUF requests have bounded prompt and output materialization, cleanup on all
  process-monitor exits, cancellable artifact hashing and an overall wall-time
  budget. Short prompts are no longer rejected merely for appearing in an argv
  substring. Stop markers spanning output chunks can terminate generation early.
- GGUF structured responses reject duplicate JSON keys, non-finite constants,
  unsupported envelopes and non-string tool identifiers. Structured/tool output
  now contributes to output-token estimates.
- Local cache keys bind an optional execution profile. GGUF profiles cover binary,
  weights, decoding/resource configuration and effective environment digest;
  successful responses carry a profile-bound execution receipt. GGUF token counts
  remain estimates, not tokenizer measurements.

## Construction obligations

This extends VOL-007 inference and FLGB-02 in their existing owners. It introduces
no provider boundary, runtime root, durable store, hosted fallback or dependency.

| Level | Implementation or remaining boundary |
| --- | --- |
| L00 Ownership | Numerical graph in `skeleton/cortex`; native contracts/receipts in `skeleton/ai/model_runtime`; backend scheduling/processes in `skeleton/ai/runtime/inference`. |
| L01 Dependencies | Existing standard-library and optional Torch paths. No new packages. |
| L02 Compatibility | Default generation policy serialization remains stable. New string-stop finish reason is declared in the existing result schema. Transformer `generate` now means new tokens, not prefix-inclusive output. |
| L03 Admission | Bounded policies, vocabulary masks, batch/concurrency limits, artifact identity, declared structured/tool schemas. |
| L04 Flow | Admit, acquire capacity, execute with cooperative interruption, bind output and usage, then publish. No automatic generation retry. |
| L05 State | Request-local CPU cache; locked shared accelerator cache; ephemeral scheduler queue. No database migration. |
| L06 Privacy | Prompts remain in private files, never argv; environment values are hashed in the profile rather than exposed by status. Model output grants no tool authority. |
| L07 Recovery | Cancelled/failed work drains owned workers; incomplete KV is discarded; a device transition requires a whole-request retry. |
| L08 Observability | Bound execution profile, terminal reason, sampled-token usage, actual accelerator rebuild/allocated-cache observations. |
| L09 Capacity | Default local concurrency one, configurable up to 32; default batch ceiling 256, configurable up to 4096. Prompt cap 4 MiB; stdout/stderr retain configured caps. Performance improvements are implementation intent, not measured claims. |
| L10 Evaluation | Explicitly deferred by operator instruction. No pass, correctness, parity, speed or model-quality claim. |
| L11 Deployment | Existing package paths. Revert this pass to roll back. New non-default configuration and special-token checkpoints require a reader supporting these additions. |
| L12 Controls | GenerationConfig, DevicePolicy, RuntimeLimits, LocalInferenceEngine limits and existing pinned GGUF configuration. |
| L13 Exit | Unverified implementation candidate; no enterprise qualification or app-wide completion percentage. |

## Remaining qualification

Real trained-model answer quality, numerical/cache parity, cancellation races,
accelerator placement, consumer-hardware behavior and release acceptance remain
unverified. Old checkpoints without special-token declarations cannot recover
undeclared EOS/BOS metadata by inference; the model owner must supply it and save
a new admitted checkpoint. Hashes bind contents and settings, not publisher trust.
