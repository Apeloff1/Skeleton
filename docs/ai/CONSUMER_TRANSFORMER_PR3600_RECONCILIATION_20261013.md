# Consumer transformer PR #3600 reconciliation

Date: 2026-10-13 UTC
PR: https://github.com/Apeloff1/Skeleton/pull/3600
PR head reviewed: `4d6eb0eea925e1cdff4a9f6d300710bbafd6f424`
Target main reviewed: `da5b7117182aca8e9f5a14a22062e6f5411c8964`

## Inheritance / preservation

This is a *supersession reconciliation*, not an assertion that the historical
PR implementation should replace newer code. The following files have the
same Git blob on the reviewed PR head and main:

- `docs/ai/CONSUMER_TRANSFORMER.md`
- `scripts/benchmark_consumer_transformer.py`
- `scripts/check_provider_bootstrap.py`
- `scripts/plan_consumer_gguf.py`
- `skeleton/ai/model_runtime/text_pipeline.py`
- `skeleton/ai/runtime/inference/__init__.py`
- `skeleton/cortex/device.py`
- `tests/ai_pipeline/test_text_pipeline.py`
- `tests/flgb/test_flgb_05_tenant_isolation.py`
- `tests/test_ai_dragon_provider_validation_resources.py`
- `tests/test_consumer_llama_budget.py`
- `tests/test_consumer_transformer_acceleration.py`

The reviewed current-main implementation is the authority for the evolved
`native_llm_runtime`, `runtime_service`, `llama_cpp`, `torch_lm`,
`transformer`, checkpoint and inference contracts. These files have
diverged since the older implementation and are deliberately **not**
overwritten or reverted by PR #3600. The checked main `torch_lm` contains
SDPA and KV handling and the referenced acceleration tests are present.

## Remaining assurance

This reconciliation does **not** establish that all enterprise model,
performance, checkpoint, memory, training and cross-device requirements
are complete. Fresh exact-main CI and benchmark evidence remain required.
No model-weight promotion, inference provider authorization or trained
model quality is inferred from this record. Earlier CI failures are not
retroactively marked passing.
