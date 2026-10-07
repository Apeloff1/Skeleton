# Native LLM runtime core

Status: **implemented on branch; verification pending**.

The runtime core is an executable path, not a provider wrapper:

```text
UTF-8 text
  -> model-bound tokenizer identity / TokenSequence
  -> token + positional embeddings
  -> stacked Pre-LN causal transformer
  -> multi-head attention + RoPE
  -> GELU/SwiGLU feed-forward blocks
  -> unembedding logits
  -> bounded top-k/top-p/temperature sampling
  -> generated token IDs
  -> model tokenizer decode
  -> deterministic inference receipt
```

## Landed execution contracts

- `tokenization.py` binds model vocabulary and optional BPE state to a stable tokenizer digest.
- `native_llm_runtime.py` exposes explicit forward, embedding, logits, sampling, batch and replay interfaces.
- Prompt overflow is fail-closed by default; left truncation requires an explicit request policy.
- Runtime limits bound context, output, batch tokens, model numeric payload, KV payload and trace retention.
- Host execution uses the native incremental KV cache. Accelerator execution does not silently mix resident accelerator weights with host cache state.
- Checkpoints are canonical-JSON content addressed, portable across devices, and bind model, tokenizer/BPE and runtime limits.
- Restore validates checkpoint integrity, model geometry, tokenizer identity, numeric finiteness and memory admission before use.
- Replay binds model digest, tokenizer digest, prompt digest, sampling digest and generated token IDs.
- Telemetry records sequence numbers, digests, counts, cache/device decisions and terminal output digests; raw prompt text is excluded.
- CPU is always supported by the reference engine. Torch/CUDA remains optional and explicit through the existing device harness.

## Verification

Focused coverage is `tests/flgb/test_flgb_02_native_llm_runtime.py`. It exercises:

1. text -> token -> embedding -> transformer -> logits;
2. positional embedding behavior and bounds;
3. continuation-only generation semantics;
4. cached/uncached decode equivalence;
5. context rejection and explicit truncation;
6. sampling/budget validation;
7. checkpoint round-trip and tamper rejection;
8. BPE identity preservation through checkpoint restore;
9. deterministic replay and drift rejection;
10. model/KV memory admission;
11. CPU binding/device-policy behavior;
12. bounded ordered batch execution;
13. telemetry redaction and accounting.

No implementation or independent-verification signature is asserted until the exact-head FLGB-02 suite passes.
