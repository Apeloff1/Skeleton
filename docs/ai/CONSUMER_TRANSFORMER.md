# Consumer-grade offline transformer and GGUF deployment

This guide documents **implemented** local paths in Skeleton. It does not
claim pretrained frontier intelligence, guaranteed performance, or a universal
fit for a listed RAM size.

## Choose the correct execution engine

| Task | Engine | Practical constraint |
|---|---|---|
| Deterministic reference debugging and small-model training | `TinyTransformer` | CPU Python arithmetic |
| Small-model training and SDPA prefill/decode | `TinyTransformer.to("torch")` | Optional PyTorch, CPU/CUDA/MPS |
| Real quantized multi-billion-parameter local inference | Offline `llama.cpp` + GGUF | Independently acquired and licensed model weights |
| Hardware planning without launching weights | `scripts/plan_consumer_gguf.py` | Requires authentic GGUF and known head geometry |

The Torch reference model does **not** load GGUF weights itself. A valid GGUF
header and a memory plan do not guarantee runtime compatibility.

## Resident KV precision and hard allocation ceiling

```python
from skeleton.cortex.transformer import TinyTransformer, KVCache
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy

# Suppose `model` is an existing admitted TinyTransformer.
# The native runtime binds the model and records the cache policy in receipts.
runtime = NativeLLMRuntime(
    model,
    device_policy=DevicePolicy(
        requested="torch", allow_fallback=False,
        kv_dtype="bf16",           # opt-in; default is fp32
        kv_limit_bytes=8 * 1024 * 1024,
    ),
)
result = runtime.infer_text("hello world")
```

For direct experimentation:

```python
model.to("torch", kv_dtype="fp16", max_kv_bytes=8 * 1024 * 1024)
cache = KVCache(model.n_layers, model.ctx)
logits = model._logits_window([1, 2, 3], cache)
actual_reserved = model._accel.kv_reserved_bytes
```

**Important distinctions:**

- FP16/BF16 changes only **resident K/V storage**. Transformer weights,
  learned embeddings, logits and attention computation remain FP32.
- Resident K/V allocation for identical shapes takes roughly half as many
  bytes as FP32 when using FP16 or BF16. Precision loss can affect logits and
  generation. FP32 remains the default.
- On devices without native compact-KV compute, K/V are converted to FP32
  for attention. This can use **additional transient memory** and may be
  slower; the hard limit controls K/V bank allocations, **not** total GPU
  memory or inference scratch.
- Compact KV is an explicit operator choice and cannot silently fall back
  to unbounded Python-cache execution. Device unavailability, OOM, or missing
  kernels must be treated as admission failures.
- GPU cache banks grow geometrically; the hard allocation check considers
  both old and new banks temporarily present during expansion.
- Shared model inference is synchronized; a trained weight mutation clears
  cached prefixes. Partially failed training blocks further use until an
  externally trusted checkpoint is restored.
- For exact reproducibility, compare native/reference logits and repeat
  on your target CUDA, CPU or Apple Silicon host. Quantized K/V results are
  not bit-for-bit identical to FP32.

## Offline GGUF admission, no downloads or execution

Obtain a locally licensed GGUF and **verify its exact geometry** from
trusted model metadata. Do not guess K/V heads or element width from a model
filename, number of parameters, or GGUF file length.

```bash
python scripts/plan_consumer_gguf.py \
  --model /path/to/local-model.gguf \
  --layers 32 --query-heads 32 --kv-heads 8 \
  --key-head-dim 128 --value-head-dim 128 \
  --key-bytes 2 --value-bytes 2 \
  --context 4096 --max-threads 8 --prefill-batch 256
```

Those dimensions are **illustrative**, not assigned to an arbitrary model.
The command validates GGUF magic/version, reads the actual file size,
queries available system memory and physical CPU cores, tightens Linux cgroup
limits, and emits JSON with the selected context, CPU threads and prefill
batch. It does not run `llama.cpp` or download weights.

A headless or unsupported host must pass known available (not total) RAM
and physical cores explicitly:

```bash
python scripts/plan_consumer_gguf.py \
  --model /path/to/local-model.gguf \
  --layers 32 --query-heads 32 --kv-heads 8 \
  --key-head-dim 128 --value-head-dim 128 \
  --ram-mib 8192 --cpu-cores 8 --context 2048 \
  --reserve-mib 512 --scratch-mib 512
```

These values are examples, not minimum requirements. The planner charges
the whole GGUF file to RAM and reserves additional OS/runtime headroom, even
when GPU layers may be offloaded. This is deliberately conservative. VRAM,
shared-unified-memory contention, mapped-file residency and backend
allocation overhead need separate verification.

## Reproducible CPU/Torch benchmark

```bash
python scripts/benchmark_consumer_transformer.py \
  --device cpu --dim 32 --heads 4 --layers 2 \
  --context 128 --prefill 32 --decode 8 --assert-parity

python scripts/benchmark_consumer_transformer.py \
  --device torch --kv-dtype bf16 --kv-limit-mib 16 \
  --dim 32 --heads 4 --layers 2 \
  --context 128 --prefill 32 --decode 8 --assert-parity
```

The benchmark reports measured prefill/decode latency, throughput,
accelerator status, actual resident KV bank bytes and reference-logit error.
It uses **untrained toy weights**. Results are only comparable on the same
machine, PyTorch version, architecture, workload, thermal/power state and
backend. A request for CUDA or MPS fails rather than reporting fallback CPU
measurements as GPU results.

## Acceptance and limits

Run `tests/test_consumer_transformer_acceleration.py` and
`tests/test_consumer_llama_budget.py` alongside the repository's P2 Local
Inference, native LM, Backend Quality, App Assembly, ARM64 and security
gates. The CPU-only workflow includes pinned PyTorch parity and BF16 cache
smoke tests. Actual CUDA/MPS validation requires matching physical runners.

No hardware-specific speedup or production readiness is asserted without
passing the exact-head CI gates and measurements on the target equipment.
