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

## Governed serving-policy decision identity

`PolicyAwareServingPlanner` validates a bounded native serving request before
policy evaluation. Request IDs must be canonical non-control UTF-8 text,
service class must be typed, token counts must honor the model-runtime token
budget, and prefix/draft availability flags must be explicit booleans. No
network/provider/model execution authority is introduced.

Serving plan v2 receipts bind every policy input: request identity, full token
counts, prefix/cache/draft facts, service class, KV/queue pressure and the
compiled runtime-policy digest. Two plans that happen to make the same
routing decision under different inputs have different receipts, so stale
pressure evidence cannot silently masquerade as a current plan. Operators
should require a fresh plan at execution admission, not treat the digest as a
signature or independent verification of reported pressure.

Focused tests:

```bash
python -m unittest tests.flgb.test_serving_policy_input_integrity -v
python -m unittest tests.flgb.test_serving_policy_era tests.flgb.test_serving_policy_pressure -v
```

### Explicit serving plan verification

`PolicyAwareServingPlanner.verify(plan, trusted_request, kv_pressure_pct=...,
queue_pressure_pct=...)` recreates the current plan under the compiled policy,
compares its digest without timing-dependent short-circuiting and requires
all typed receipt fields to match. A stale pressure record, changed policy,
different request or altered receipt is refused. The caller must provide
trusted fresh inputs; merely comparing to the plan's own claimed inputs would
not be a meaningful authority boundary. The verifier does **not** contact
providers, mutate scheduling state or independently authenticate telemetry.
