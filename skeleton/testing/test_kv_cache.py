from __future__ import annotations

import pytest

from skeleton.kv_cache import (
    CacheTier,
    KVCacheConfig,
    KVCacheManager,
    KVNamespace,
    KVPageInput,
)


def namespace(**overrides):
    values = {"model_id": "test/model", "trust_domain": "tenant-a"}
    values.update(overrides)
    return KVNamespace(**values)


def pages(count: int, *, size: int = 64, tier: CacheTier = CacheTier.GPU, prefix: str = "p"):
    return [
        KVPageInput(handle=f"{prefix}-{index}", size_bytes=size, tier=tier, recompute_cost=index + 1)
        for index in range(count)
    ]


def test_longest_prefix_match_reuses_paged_chain():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4, max_bytes=4096))
    ns = namespace()
    keys = cache.commit_prefix(range(10), pages(3), ns)

    match = cache.lookup(range(12), ns)

    assert len(keys) == 3
    assert match.matched_tokens == 8
    assert match.handles == ("p-0", "p-1")
    assert match.hit_ratio == pytest.approx(8 / 12)
    assert cache.stats().token_hit_ratio == pytest.approx(8 / 12)


def test_full_hit_reuses_partial_tail_only_when_exact():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4))
    ns = namespace()
    cache.commit_prefix(range(10), pages(3), ns)

    exact = cache.lookup(range(10), ns)
    extended = cache.lookup(range(11), ns)

    assert exact.full_hit is True
    assert exact.matched_tokens == 10
    assert extended.matched_tokens == 8


def test_namespace_fields_and_cache_salt_isolate_reuse():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4))
    left = namespace(cache_salt="private-a")
    right = namespace(cache_salt="private-b")
    adapter = namespace(cache_salt="private-a", adapter_id="lora-v2")
    cache.commit_prefix(range(8), pages(2), left)

    assert cache.lookup(range(8), left).full_hit
    assert cache.lookup(range(8), right).matched_tokens == 0
    assert cache.lookup(range(8), adapter).matched_tokens == 0


def test_block_extra_fingerprint_protects_multimodal_or_backend_specific_state():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4))
    ns = namespace()
    stored = [
        KVPageInput(handle="text", size_bytes=64),
        KVPageInput(handle="image", size_bytes=64, extra_fingerprint="image:sha256:abc"),
    ]
    cache.commit_prefix(range(8), stored, ns)

    plain = cache.lookup(range(8), ns)
    enriched = cache.lookup(range(8), ns, block_extras=("", "image:sha256:abc"))

    assert plain.matched_tokens == 4
    assert enriched.full_hit
    assert enriched.handles == ("text", "image")


def test_duplicate_prefix_arbitrates_to_existing_page_and_tracks_dedup():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4))
    ns = namespace()
    first = cache.commit_prefix(range(4), [KVPageInput("original", 64, recompute_cost=1)], ns)
    second = cache.commit_prefix(range(4), [KVPageInput("duplicate", 64, recompute_cost=9)], ns)

    assert first == second
    assert cache.lookup(range(4), ns).handles == ("original",)
    assert cache.stats().deduplicated_pages == 1


def test_eviction_is_bounded_and_preserves_pinned_subtree():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4, max_bytes=192, max_entries=3))
    ns = namespace()
    pinned_keys = cache.commit_prefix(range(8), pages(2, prefix="pin"), ns, pin=True)
    cache.commit_prefix(range(100, 108), pages(2, prefix="other"), ns)

    stats = cache.stats()
    assert stats.resident_bytes <= 192
    assert stats.resident_pages <= 3
    assert cache.lookup(range(8), ns).full_hit
    assert all(key in cache.lookup(range(8), ns).page_keys for key in pinned_keys)


def test_release_allows_budget_enforcement_after_pin():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4, max_bytes=64, max_entries=1))
    ns = namespace()
    keys = cache.commit_prefix(range(8), pages(2, prefix="pin"), ns, pin=True)
    assert cache.stats().resident_bytes == 128

    cache.release(keys)

    assert cache.stats().resident_bytes <= 64
    assert cache.stats().resident_pages <= 1


def test_transaction_is_invisible_until_commit_and_rollback_discards():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4))
    ns = namespace()

    tx = cache.transaction(ns).stage(range(8), pages(2))
    assert cache.lookup(range(8), ns).matched_tokens == 0
    tx.rollback()
    assert cache.lookup(range(8), ns).matched_tokens == 0

    committed = cache.transaction(ns).stage(range(8), pages(2)).commit()
    assert len(committed) == 2
    assert cache.lookup(range(8), ns).full_hit


def test_context_manager_commits_success_and_rolls_back_exception():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4))
    ns = namespace()

    with cache.transaction(ns) as tx:
        tx.stage(range(4), pages(1, prefix="ok"))
    assert cache.lookup(range(4), ns).full_hit

    with pytest.raises(RuntimeError):
        with cache.transaction(ns) as tx:
            tx.stage(range(100, 104), pages(1, prefix="bad"))
            raise RuntimeError("reject speculation")
    assert cache.lookup(range(100, 104), ns).matched_tokens == 0


def test_trust_domain_quota_is_enforced_without_cross_tenant_eviction_bias():
    config = KVCacheConfig(
        block_size_tokens=4,
        max_bytes=1024,
        max_entries=100,
        trust_domain_max_bytes=128,
    )
    cache = KVCacheManager(config)
    tenant_a = namespace(trust_domain="a")
    tenant_b = namespace(trust_domain="b")

    cache.commit_prefix(range(8), pages(2, prefix="a"), tenant_a)
    cache.commit_prefix(range(100, 108), pages(2, prefix="b"), tenant_b)
    cache.commit_prefix(range(200, 204), pages(1, prefix="a2"), tenant_a)

    assert cache.lookup(range(100, 108), tenant_b).full_hit
    assert cache.stats().resident_bytes <= 256


class Storage:
    def __init__(self):
        self.moves = []
        self.releases = []

    def move(self, handle, source, target):
        self.moves.append((handle, source, target))
        return f"{handle}@{target.value}"

    def release(self, handle, tier):
        self.releases.append((handle, tier))


def test_tier_migration_and_cache_aware_route_score():
    storage = Storage()
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4), storage=storage)
    ns = namespace()
    keys = cache.commit_prefix(
        range(8),
        pages(2, tier=CacheTier.CPU),
        ns,
    )

    before = cache.estimate_reuse(range(8), ns)
    moved = cache.migrate(keys, CacheTier.GPU)
    after = cache.estimate_reuse(range(8), ns)

    assert moved == keys
    assert before.route_score == pytest.approx(0.78)
    assert after.route_score == pytest.approx(1.0)
    assert after.hottest_tier == CacheTier.GPU
    assert cache.lookup(range(8), ns).handles == ("p-0@gpu", "p-1@gpu")


def test_invalidation_releases_namespace_only():
    storage = Storage()
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4), storage=storage)
    a = namespace(trust_domain="a")
    b = namespace(trust_domain="b")
    cache.commit_prefix(range(4), pages(1, prefix="a"), a)
    cache.commit_prefix(range(4), pages(1, prefix="b"), b)

    assert cache.invalidate_namespace(a) == 1
    assert cache.lookup(range(4), a).matched_tokens == 0
    assert cache.lookup(range(4), b).full_hit
    assert storage.releases == [("a-0", CacheTier.GPU)]


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        KVCacheConfig(block_size_tokens=True)
    with pytest.raises(ValueError):
        KVCacheConfig(max_bytes=0)
    with pytest.raises(ValueError):
        KVPageInput(handle="x", size_bytes=0)
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4))
    ns = namespace()
    with pytest.raises(ValueError):
        cache.commit_prefix([-1], [KVPageInput("x", 1)], ns)
    with pytest.raises(ValueError, match="expected 2 page handles"):
        cache.commit_prefix(range(8), [KVPageInput("x", 1)], ns)
