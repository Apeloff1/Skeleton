# Hyper KV Cache — 50-Step Evolution

`HyperKVCache` is a provider- and tensor-runtime-neutral KV-cache control plane. Tensor pages are opaque bytes at this boundary; CUDA/ROCm/CPU/NVMe adapters can own physical allocation while this module owns safe reuse, policy, topology, verification, and telemetry.

## 50 evolution steps

1. Paged-block allocator contract.
2. Zero-copy opaque payload boundary.
3. Hot-page locality layout.
4. Prefix hashing.
5. Cross-request prefix reuse.
6. Content-addressed deduplication.
7. Token-selective longest-prefix lookup.
8. Attention-score telemetry.
9. Recency/frequency scoring.
10. Heavy-hitter retention.
11. Sink/pinned block retention.
12. Independent K/V precision plans.
13. Per-channel quantization metadata.
14. Mixed precision by layer/head group.
15. Full-precision residual window.
16. Pressure-adaptive precision policy hook.
17. Cold-block compression.
18. Compression-benefit admission.
19. Compact positional identity metadata.
20. System-prefix deduplication.
21. HOT/WARM/COLD tier abstraction.
22. Backend-ready prefetch API.
23. Speculative prefetch.
24. High/low-watermark eviction.
25. SLA-aware admission scoring.
26. Per-tenant byte quotas.
27. Priority classes.
28. TTL plus pinning.
29. Semantic segment tags.
30. Retrieval-driven prefix rehydration.
31. RoPE compatibility fingerprint.
32. Model/revision/layer/head fingerprint.
33. Coherence/version tags.
34. SHA-256 integrity verification.
35. Stale/poison invalidation hooks.
36. Transactional speculative append.
37. Speculative rollback.
38. Branch inheritance and copy-on-write indexing.
39. KVARG verifier/arbitration graph.
40. Weighted disagreement reconciliation.
41. GQA/MQA head-group identity.
42. Scheduler-friendly batch-prefix interface.
43. Tier rebalance/defragmentation policy.
44. Backpressure and byte budgets.
45. Capacity-policy hooks.
46. Hit/reuse/dedup/compression telemetry.
47. Closed-loop adaptive policy controller.
48. Rendezvous distributed sharding.
49. Deterministic replica failover ordering.
50. Autotuning plus invariant-ready snapshots/tests.

## Safety invariants

A cache hit is reusable only when the model/revision/layer/head-group/RoPE/layout fingerprint matches. Payloads are checksum-verified before reuse. Expired non-pinned entries are evicted. A verifier graph may veto any otherwise-valid reuse. Speculative work can be rolled back without destroying parent-branch state.

## Runtime integration

The current implementation intentionally does not require NumPy, PyTorch, CUDA, vLLM, or a vendor SDK. `QuantizationPlan` expresses the physical K/V representation requested from a backend; the control plane does not pretend to quantize arbitrary tensor bytes itself. Likewise, HOT/WARM/COLD are logical tiers until a runtime adapter maps them to GPU VRAM, host RAM, local NVMe, or a remote cache service.

Recommended integration order:

- model runtime constructs `KVIdentity` from the loaded model revision, attention layer/head group, RoPE parameters, and layout version;
- scheduler calls `best_prefix()` before prefill and `put()` after materializing reusable pages;
- speculative decoding uses `fork()`, `begin()`, `commit()`, and `rollback()`;
- verifier/CAG/MAG-style checks register through `KVArbitrationGraph`;
- serving telemetry periodically calls `autotune()` with observed memory pressure and hit rate;
- multi-node serving uses `RendezvousShardRouter.rank()` for primary and failover placement.

## Validation

Regression coverage is in `skeleton/testing/test_hyper_kv_cache.py` and covers dedup/reuse, branch inheritance, rollback, TTL/pinning, arbitration rejection, corruption eviction, tenant quotas, shard determinism, autotuning, and the exact 50-item evolution manifest.
