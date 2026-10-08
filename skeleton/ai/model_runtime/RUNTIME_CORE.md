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

This is implementation evidence only. FLGB-02 stays `implemented-pending-verification`
until exact-head CI, dependency closure and independent verification succeed. No
masterplan completion signature is asserted by file existence or by this document.

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
