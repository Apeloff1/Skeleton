# CPU native KV spill and restore (v1)

`NativeLLMRuntime.spill_cpu_kv(cache, store)` persists the actual reference
transformer KV vectors, token window, last logits, window-relative position
and reset count to an immutable content-addressed file. Its counterpart
`restore_cpu_kv(digest, store)` verifies the complete record and reconstructs
a new `KVCache` bound to the same live native model revision. The cache can
then be passed to `TinyTransformer._logits_window` without recomputing the
unchanged cached prefix.

```python
from skeleton.ai.model_runtime.cpu_kv_spill import CpuKVSpillStore
from skeleton.cortex.transformer import KVCache

store = CpuKVSpillStore("./private-cpu-kv")
cache = KVCache(runtime.model.n_layers, runtime.limits.max_context)
logits = runtime.model._logits_window(prompt_ids, cache)
digest = runtime.spill_cpu_kv(cache, store)
restored = runtime.restore_cpu_kv(digest, store)
assert runtime.model._logits_window(prompt_ids, restored) == logits
```

This is a **CPU-only exact-reference cache**, not a Metal/CUDA/ROCm tensor
migration mechanism. Accelerator-resident or merely mirrored cache occupancy
is rejected, as are model/tokenizer drift, changed architecture, malformed
layers, NaN/Infinity, noncanonical JSON, wrong shapes, stale revisions,
symlinks, truncated objects and disk-budget overruns. It grants no inference,
tool, filesystem or model activation authority. The caller must independently
admit the request, enforce cancellation and deadline, and retain the returned
digest in its own authenticated durable job ledger.

Storage is atomic hard-link publication of an fsynced temporary file; a crash
cannot publish partial bytes. Repeated identical snapshots have the same
SHA-256 identity. No mutable latest pointer is maintained. Root directories
must be private and operator-controlled. The hash is an integrity check, **not
a publisher signature or encryption**; do not store sensitive KV tensors on
shared or untrusted storage. Free-space reserve is a best-effort preflight,
not a replacement for filesystem quotas. Windows does not have the same
O_NOFOLLOW symlink-race protection as POSIX.

Focused tests:

```bash
python -m unittest tests.flgb.test_cpu_kv_spill -v
```

The implementation is not device qualified, and no GPU or release
qualification is claimed.
