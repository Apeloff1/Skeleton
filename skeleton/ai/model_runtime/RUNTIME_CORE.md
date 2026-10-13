# Native LLM runtime core

This runtime is the executable FLGB-02 bridge from governed text input to the
repository-owned causal transformer and back to generated text. It does not
create a second model implementation. The numerical engine remains
`skeleton/cortex/transformer.py`; this plane makes that engine safe to serve.

## Implemented on this branch

- bounded text/chunk ingestion with exact source digests and stable tokenizer identity;
- deterministic context windows, token batching and canonical token-sequence serialization;
- explicit prompt IDs versus newly generated IDs (no prefix/output ambiguity);
- incremental KV decode and uncached reference decode through the same transformer;
- temperature/top-k/top-p/seed/stop-token decoding with fail-closed validation;
- deterministic streaming events and replay receipts;
- portable model/checkpoint identity, shape validation and tamper detection;
- explicit re-admission after model-weight mutation;
- logical model/KV memory admission and batch token budgets;
- CPU-default placement with bounded optional accelerator fallback policy;
- checkpoint JSON round-trip including attached BPE state;
- architecture and health snapshots for embeddings, position handling, heads, layers and FFN shape.

## Authority and completion status

For local backend execution, `LocalInferenceEngine(model, max_concurrency=1,
max_batch_size=256)` bounds active model calls and direct batches. Concurrency
can be explicitly raised up to 32; batch size up to 4096. Raising concurrency
can multiply GGUF process/model memory, so the default remains one. Queued
calls can cancel before acquiring execution capacity. Failed batches drain
their siblings before returning an error.

`LocalInferenceScheduler` rejects a full queue rather than allowing blocked
submissions to outlive shutdown. Cancelling a submitted future cancels that
item's inference task. `close()` drains admitted work and can be awaited again
if an earlier shutdown waiter was cancelled. There is no automatic model retry.

Local cache hits retain isolated copies of structured/tool JSON and bind the
backend's execution profile when available. Cancellation and deadline results
are not cached. GGUF artifacts are readmitted before a cached answer is reused.

This is implementation evidence only. FLGB-02 stays `implemented-pending-verification`
until exact-head CI, dependency closure and independent verification succeed. No
masterplan completion signature is asserted by file existence or by this document.

## Generation and interruption controls

`GenerationConfig` accepts `repetition_penalty`, `presence_penalty`,
`frequency_penalty`, `penalty_window`, `min_new_tokens`, `suppress_token_ids`,
`stop_strings` and `include_stop_tokens` in addition to the existing sampler
options. Non-default settings are included in the configuration digest. The
penalty window covers recent prompt and generated IDs. Minimum token count
suppresses terminal token IDs until the minimum has been sampled; text stops
are considered after that minimum. Text before an earlier matching marker can
still be shorter than the sampled-token count.

```python
config = GenerationConfig.from_dict(
    {
        "max_new_tokens": 64,
        "temperature": 0.7,
        "top_p": 0.9,
        "repetition_penalty": 1.1,
        "penalty_window": 64,
        "stop_strings": ["\nuser:"],
        "include_stop_tokens": False,
    },
    limits=runtime.limits,
    vocab_size=runtime.tokenizer.vocab_size,
)
result = runtime.generate(prompt, config)
```

This example requires an already-admitted trained runtime with a sufficient
output budget. It does not initialize trained weights or establish answer quality.

Inference, generation, feed, batch and streaming entrypoints accept an optional
`interrupt` callback. It must
return normally to continue or raise to abort. Use the stream as a context manager
to release partial generator state. Cooperative interruption occurs between CPU
layers/attention rows and Torch layers/configured prefill chunks, including while
waiting for a shared accelerator. A kernel, snapshot or some tokenization work
can remain non-interruptible until its current operation finishes.

Token IDs remain raw sampled IDs, including a terminal token. With string stops,
token-event text is buffered and the completed event contains the final visible
text; this prevents exposing an incomplete stop marker. Without string stops,
token-event text remains vocabulary pieces rather than a guaranteed detokenized
text stream. `GenerationResult.text` is the authoritative displayed answer.

The native adapter recognizes a declared EOS token and excludes its text. Optional
`unk`/`pad`/`bos`/`eos` declarations are preserved in model snapshots; no EOS token
is guessed from a token's spelling. Changing the runtime binding while generating
aborts the request instead of issuing a receipt for mixed model/device execution.

The October 13 inference pass is unverified: no checks or tests were run at the
operator's request. See `docs/plan/AI_INFERENCE_TRANSFORMER_2026-10-13.md`.

## Focused validation

```bash
python -m unittest tests.flgb.test_flgb_02_tokenization_pipeline -v
python -m unittest tests.flgb.test_flgb_02_native_llm_runtime -v
python -m unittest discover -s tests/flgb -p 'test_flgb_02_*.py' -v
```

## Bounded serving-control preflight and observations

The deterministic SLO resource planner caps prefill chunk materialization to
`max_prefill_chunks` (default 4096). Inputs that exceed the bound return a
fail-closed `prefill_chunk_limit_exceeded` decision with no chunk allocation
and zero claimed KV reservation. A `ResourcePlan` is **not** a KV allocation;
serving callers must verify `admitted`, then independently enforce runtime
limits before generation. The plan digest binds planner configuration.

The EWMA runtime estimator rejects repeated request identities within a
bounded recent-identity window of `max_samples`. This is a recent-replay
fence, **not** cross-process exactly-once storage. Deployments need durable
request deduplication before accepting retried observations. Serving telemetry
windows have finite record capacity and reject new records when full rather
than silently dropping old SLO evidence. An operator should rotate or persist
the window explicitly and preserve its digest. These mechanisms grant no
model execution, provider credentials, network, or release-promotion authority.

Focused regression:

```bash
python -m unittest tests.flgb.test_serving_control_adversarial_boundaries -v
python -m unittest tests.flgb.test_slo_planner tests.flgb.test_runtime_feedback tests.flgb.test_serving_telemetry tests.flgb.test_closed_loop_serving -v
```

This evidence does not independently qualify FLGB-02 or sign a masterplan volume.

## Explicit feedback checkpoint and restart recovery

`DeterministicRuntimeEstimator.checkpoint()` returns an operator-managed JSON
record with a version tag, estimator configuration, learned estimate, sample
counts, bounded recent identities, and a deterministic SHA-256 digest.
`DeterministicRuntimeEstimator.from_checkpoint(record)` rejects unknown fields,
missing fields, invalid primitive types, negative counts, mismatched identity
horizons, duplicate identities, incompatible limits, and modified digests.
Restored controllers retain the previous estimate and recent replay fence.

The digest detects accidental or unsophisticated modification but **does not
authenticate a publisher**. Production callers must arrange trusted, atomic
persistence and independent source authentication. A checkpoint does not grant
serving authority, and this in-process replay fence does not replace a durable
cross-worker idempotency ledger. Controlled rollback must be explicit.

## Evidence digest input binding

SLO plan v2 digests cover planner policy **and** the input prompt count,
forecast, performance objectives, KV capacity/occupancy and queue pressure.
A successful decision from a stale pressure snapshot cannot be substituted for
a new decision with matching aggregate output fields. Serving telemetry v2
binds metric thresholds and a canonical digest of sorted individual
observations (request identity, latency, tokens and prefix reuse), preventing
summaries of different cohorts from being treated as identical evidence.
Raw telemetry identifiers must remain in a governed data store; the exported
metrics expose only the observation digest. No cryptographic source authenticity
is implied by hashing.
