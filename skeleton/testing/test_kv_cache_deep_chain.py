from __future__ import annotations

from skeleton.kv_cache import KVCacheConfig, KVCacheManager, KVNamespace, KVPageInput


def _namespace(model_id: str) -> KVNamespace:
    return KVNamespace(model_id=model_id, trust_domain="deep-chain")


def _pages(count: int, prefix: str) -> list[KVPageInput]:
    return [KVPageInput(handle=f"{prefix}-{index}", size_bytes=1) for index in range(count)]


def test_deep_chain_pin_protection_and_eviction_do_not_recurse() -> None:
    depth = 1_200
    cache = KVCacheManager(
        KVCacheConfig(
            block_size_tokens=1,
            max_bytes=depth + 1,
            max_entries=depth + 1,
        )
    )
    protected = _namespace("deep/protected")
    spill = _namespace("deep/spill")

    keys = cache.commit_prefix(range(depth), _pages(depth, "protected"), protected)
    cache.pin([keys[-1]])

    # Adding a second chain crosses the entry budget. The eviction scan must
    # discover that the first chain contains a pinned descendant without a
    # recursive walk that exceeds Python's normal recursion depth.
    cache.commit_prefix(range(10_000, 10_002), _pages(2, "spill"), spill)

    assert cache.lookup(range(depth), protected).full_hit
    assert cache.stats().resident_pages <= depth + 1
    assert cache.audit().valid


def test_deep_chain_clear_is_iterative_and_leaves_indexes_consistent() -> None:
    depth = 1_200
    cache = KVCacheManager(
        KVCacheConfig(
            block_size_tokens=1,
            max_bytes=depth + 8,
            max_entries=depth + 8,
        )
    )
    ns = _namespace("deep/clear")
    cache.commit_prefix(range(depth), _pages(depth, "clear"), ns)

    assert cache.clear() == depth
    assert cache.stats().resident_pages == 0
    assert cache.stats().resident_bytes == 0
    assert cache.audit().valid
