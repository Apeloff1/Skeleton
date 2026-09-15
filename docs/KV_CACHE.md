# KV Cache Control Plane

Skeleton now has an engine-agnostic paged KV-cache control plane in `skeleton.kv`.
It deliberately does not pretend that remote API providers expose raw K/V tensors. Instead, local inference engines can bind their physical page handles through `KVStorageAdapter`, while Skeleton owns identity, safety, reuse, arbitration, scheduling metadata, tiering policy, and invariants.

## Architecture

A cache entry is a hash-chained page. Its identity includes:

- the complete semantic namespace (`model_id`, revision, tokenizer, adapter, RoPE configuration, attention configuration, KV dtype, tensor layout);
- trust-domain and optional `cache_salt` isolation;
- the parent page hash, so the same token block under a different prefix cannot alias;
- exact token IDs;
- an optional per-page extra fingerprint for multimodal inputs or backend-specific state.

The physical page itself is opaque to Skeleton. A backend can use a CUDA page pointer, allocator ID, CPU buffer, NVMe object, distributed-cache locator, recurrent state checkpoint, or another handle.

## Reuse path

`KVCacheManager.lookup()` performs longest-prefix matching at page granularity. Full and partial prompt reuse are separated, and partial tail pages are reusable only when the tail is exact. Verification checks the namespace, parent edge, token block, and extra fingerprint before a page is returned.

`estimate_reuse()` is side-effect free and returns a locality-weighted route score. Schedulers can therefore route a request toward a worker that already owns its prefix instead of treating cache locality as invisible state.

## KVARG: verification, arbitration, reconciliation graph

The cache is represented as a dependency graph whose edges are parent-hash relationships.

- **Verification:** exact semantic and token checks defend against accidental hash/namespace misuse.
- **Arbitration:** duplicate page commits preserve the canonical resident page, merge recomputation/retention value, and release redundant backend pages when an adapter is available.
- **Reconciliation:** eviction cascades through dependent descendants; pinned descendants protect their ancestors; `audit()` checks graph reachability, secondary indexes, and byte accounting.

This keeps a child page from surviving after its required prefix state has disappeared.

## Adaptive retention

Eviction is not plain LRU. The retention score combines:

- observed request frequency;
- page hit count;
- recency with exponential half-life decay;
- estimated recomputation cost;
- explicit `retention_bias` for prompt-end / agentic checkpoints;
- physical tier locality;
- page size cost.

The frequency sketch decays periodically so old traffic does not dominate forever. Global byte/page budgets and optional per-trust-domain byte quotas are enforced independently.

## Multi-tier KV

`CacheTier` models `GPU -> CPU -> NVMe -> REMOTE` placement. `KVStorageAdapter` is the physical boundary for move and release operations. The manager provides:

- explicit migration;
- hot-page prefetch candidate ranking;
- route scoring that prefers warmer tiers;
- cleanup-error containment and metrics;
- quantization metadata without coupling the control plane to a tensor library.

A production vLLM/SGLang/custom adapter should perform asynchronous copies and return the resulting opaque handle from `move()`.

## Speculative and branch decoding

`KVCacheTransaction` stages a prefix privately and exposes it only on commit. Rollback discards the staged control-plane state. Because manager mutation is protected by one re-entrant lock, readers cannot observe a partially committed page chain.

Backend engines remain responsible for reclaiming speculative physical pages that were never submitted to the manager after rollback.

## Security boundaries

Never reuse KV state across semantically different model configurations. Populate `KVNamespace` with every field that changes tensor meaning or layout. In multi-tenant deployments, use a separate `trust_domain` and unpredictable `cache_salt` per trust group so timing differences do not reveal another tenant's cached prefix.

## Integration example

```python
from skeleton.kv_cache import KVCacheConfig, KVCacheManager, KVNamespace, KVPageInput

cache = KVCacheManager(KVCacheConfig(block_size_tokens=16, max_bytes=8 << 30))
namespace = KVNamespace(
    model_id="org/model",
    model_revision="sha256:...",
    tokenizer_id="org/tokenizer",
    rope_signature="rope:base=10000:scale=1",
    attention_signature="full-attention:v1",
    kv_dtype="fp8",
    tensor_layout="paged-v1",
    trust_domain="tenant-42",
    cache_salt="opaque-random-salt",
)

# `engine_pages` are opaque handles returned by the serving engine.
cache.commit_prefix(
    prompt_token_ids,
    [KVPageInput(handle=page, size_bytes=page_bytes) for page in engine_pages],
    namespace,
)

match = cache.lookup(next_prompt_token_ids, namespace)
engine.resume_from_pages(match.handles, matched_tokens=match.matched_tokens)
```

## Validation

Focused tests cover:

- longest-prefix and full-prefix hits;
- partial-tail correctness;
- model/adapter/salt isolation;
- extra fingerprints for multimodal/backend state;
- duplicate arbitration;
- bounded adaptive eviction;
- pinned dependency subtrees;
- speculative commit/rollback;
- trust-domain quotas;
- tier migration and cache-aware route scoring;
- namespace invalidation;
- backend cleanup failures;
- graph/accounting audit;
- concurrent lookup/commit integrity.

The implementation is a SOTA-oriented control plane, not a benchmark claim. End-to-end performance still depends on the serving backend, allocator, attention kernels, network/storage tier, workload locality, and scheduler. Before calling a concrete deployment state of the art, benchmark TTFT, inter-token latency, tokens/s, cache-hit tokens, migration bandwidth, memory amplification, and p50/p95/p99 latency against the target vLLM/SGLang configuration on the same model and hardware.

## Next backend-specific frontier

The highest-value follow-up is a native adapter for the chosen local inference engine. That adapter should add asynchronous page migration, distributed remote lookup, copy/computation overlap, backend event completion, and hardware-aware KV quantization. The control-plane API is intentionally structured so those capabilities can land without changing cache identity or scheduler-facing semantics.
