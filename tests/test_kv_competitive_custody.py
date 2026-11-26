"""Canonical and mirrored cache custody and bounded local-tier pressure."""
import importlib

import pytest


@pytest.fixture(params=["skeleton.kv", "skeleton.ai.runtime.inference.kv"])
def kv(request):
    return importlib.import_module(request.param)


class Storage:
    def __init__(self):
        self.moves = []
        self.releases = []
        self.fail = False

    def move(self, handle, source, target):
        if self.fail:
            raise OSError("device unavailable")
        self.moves.append((handle, source, target))
        return ("moved", handle)

    def release(self, handle, tier):
        self.releases.append((handle, tier))


def ns(kv, label="alice"):
    return kv.KVNamespace("model", model_revision="weights", tokenizer_id="tokens",
                          trust_domain=label, cache_salt="private-session")


def manager(kv, *, maximum=128, domain=None, storage=None, clock=None):
    options = {"storage": storage}
    if clock is not None:
        options["clock"] = clock
    return kv.KVCacheManager(kv.KVCacheConfig(block_size_tokens=2, max_bytes=maximum,
                              trust_domain_max_bytes=domain), **options)


def put(kv, cache, tokens, scope, *, pin=False, size=16, quantization="native"):
    pages = [kv.KVPageInput(object(), size, quantization=quantization)
             for _ in range((len(tokens)+1)//2)]
    return cache.commit_prefix(tokens, pages, scope, pin=pin)


def test_atomic_prefix_lease_blocks_migration_and_destruction(kv):
    storage = Storage()
    cache = manager(kv, storage=storage)
    scope = ns(kv)
    keys = put(kv, cache, [1, 2, 3, 4], scope)
    with cache.acquire_prefix([1, 2, 3, 4], scope) as match:
        assert match.full_hit
        assert cache.migrate(keys, kv.CacheTier.CPU) == ()
        with pytest.raises(RuntimeError, match="active page leases"):
            cache.invalidate_namespace(scope)
        with pytest.raises(RuntimeError, match="active page leases"):
            cache.clear()
    assert cache.migrate(keys, kv.CacheTier.CPU) == keys
    assert cache.invalidate_namespace(scope) == 2
    assert cache.audit().valid


def test_lease_releases_after_exception(kv):
    cache = manager(kv)
    scope = ns(kv)
    put(kv, cache, [1, 2], scope)
    with pytest.raises(KeyError):
        with cache.acquire_prefix([1, 2], scope):
            raise KeyError("decode interrupted")
    assert cache.clear() == 1


def test_pinned_limits_preflight_is_atomic(kv):
    storage = Storage()
    cache = manager(kv, maximum=64, domain=32, storage=storage)
    scope = ns(kv)
    put(kv, cache, [1, 2], scope, pin=True)
    with pytest.raises(RuntimeError, match="budget"):
        put(kv, cache, [1, 2, 3, 4, 5, 6], scope, pin=True)
    assert cache.stats().resident_pages == 1
    assert storage.releases == []
    assert cache.audit().valid


def test_incompatible_quantization_does_not_replace_cached_pages(kv):
    cache = manager(kv)
    scope = ns(kv)
    put(kv, cache, [1, 2], scope)
    with pytest.raises(RuntimeError, match="semantic mismatch"):
        put(kv, cache, [1, 2, 3, 4], scope, quantization="q4")
    assert cache.stats().resident_pages == 1
    assert cache.audit().valid


def test_tier_pressure_respects_leases_scopes_and_byte_limits(kv):
    storage = Storage()
    cache = manager(kv, storage=storage)
    owner = ns(kv)
    other = ns(kv, "bob")
    put(kv, cache, [1, 2, 3, 4], owner)
    put(kv, cache, [7, 8], other)
    with cache.acquire_prefix([1, 2], owner):
        receipt = cache.rebalance_local(source=kv.CacheTier.GPU, target=kv.CacheTier.CPU,
            source_ceiling_bytes=0, target_ceiling_bytes=16, max_move_bytes=16,
            namespace=owner)
        assert receipt == {"moved_pages": 1, "moved_bytes": 16, "source_bytes": 32,
                           "target_bytes": 16, "remaining_pressure_bytes": 32,
                           "storage_errors": 0}
        assert cache.lookup([7, 8], other).tiers == (kv.CacheTier.GPU,)
        assert cache.lookup([1, 2], owner).tiers == (kv.CacheTier.GPU,)
    assert cache.audit().valid


def test_failed_migration_retains_source_and_reports_pressure(kv):
    storage = Storage()
    storage.fail = True
    cache = manager(kv, storage=storage)
    scope = ns(kv)
    put(kv, cache, [1, 2], scope)
    receipt = cache.rebalance_local(source=kv.CacheTier.GPU, target=kv.CacheTier.NVME,
        source_ceiling_bytes=0, target_ceiling_bytes=64, max_move_bytes=64)
    assert receipt["storage_errors"] == 1 and receipt["moved_bytes"] == 0
    assert cache.lookup([1, 2], scope).tiers == (kv.CacheTier.GPU,)
    assert cache.audit().valid


def test_remote_spill_not_implicitly_permitted(kv):
    cache = manager(kv, storage=Storage())
    with pytest.raises(ValueError, match="local cache tiers"):
        cache.rebalance_local(source=kv.CacheTier.GPU, target=kv.CacheTier.REMOTE,
            source_ceiling_bytes=0, target_ceiling_bytes=64, max_move_bytes=64)


def test_advisory_estimate_does_not_refresh_recency(kv):
    tick = [0.0]
    cache = manager(kv, clock=lambda: tick[0])
    scope = ns(kv)
    keys_a = put(kv, cache, [1, 2], scope)
    tick[0] = 100
    keys_b = put(kv, cache, [3, 4], scope)
    tick[0] = 200
    assert cache.estimate_reuse([1, 2], scope).matched_tokens == 2
    assert cache.prefetch_candidates(target=kv.CacheTier.CPU) == keys_b + keys_a
