from __future__ import annotations

import pytest

from skeleton.frontier.hyper_kv_cache import (
    AdmissionContext,
    CacheIntegrityError,
    CachePolicy,
    HYPER_KV_EVOLUTION,
    HyperKVCache,
    KVArbitrationGraph,
    KVIdentity,
    RendezvousShardRouter,
)


def _identity() -> KVIdentity:
    return KVIdentity("jeeves", "r1", 3, 0, "rope-v1")


def test_put_get_and_dedup() -> None:
    cache = HyperKVCache(CachePolicy(max_bytes=8192, compression_min_bytes=32))
    payload = b"A" * 512
    first = cache.put(_identity(), [1, 2, 3], payload)
    second = cache.put(_identity(), [1, 2, 3], payload)

    assert first == second
    hit = cache.get(_identity(), [1, 2, 3])
    assert hit is not None
    assert hit.payload == payload
    assert cache.metrics.dedup_hits == 1
    assert cache.metrics.hits == 1


def test_best_prefix_reuses_parent_branch() -> None:
    cache = HyperKVCache(CachePolicy(max_bytes=8192))
    cache.put(_identity(), [1, 2], b"parent")
    cache.fork("spec")

    hit = cache.best_prefix(_identity(), [1, 2, 3, 4], branch="spec")

    assert hit is not None
    assert hit.payload == b"parent"


def test_transaction_rollback_removes_speculative_blocks() -> None:
    cache = HyperKVCache(CachePolicy(max_bytes=8192))
    transaction = cache.begin()
    digest = cache.put(_identity(), [9], b"speculative")

    assert digest is not None
    assert cache.commit(transaction) == 1
    assert cache.rollback(transaction) == 1
    assert cache.get(_identity(), [9]) is None


def test_ttl_respects_pinning() -> None:
    now = [100.0]
    cache = HyperKVCache(
        CachePolicy(max_bytes=8192, default_ttl_seconds=1),
        clock=lambda: now[0],
    )
    digest = cache.put(_identity(), [1], b"x")
    assert digest is not None
    cache.pin(digest)
    now[0] += 2

    assert cache.get(_identity(), [1]) is not None
    cache.pin(digest, False)
    assert cache.get(_identity(), [1]) is None


def test_arbitration_can_reject_reuse() -> None:
    def reject(_block):
        return False, 1.0, "unsafe"

    cache = HyperKVCache(
        CachePolicy(max_bytes=8192),
        arbitration=KVArbitrationGraph([reject]),
    )
    cache.put(_identity(), [1], b"x")

    assert cache.get(_identity(), [1]) is None
    assert cache.metrics.verifier_disagreements == 1


def test_integrity_failure_evicts_corrupt_block() -> None:
    cache = HyperKVCache(CachePolicy(max_bytes=8192))
    digest = cache.put(_identity(), [1], b"x")
    assert digest is not None
    cache._blocks[digest].stored_payload = b"y"

    with pytest.raises(CacheIntegrityError):
        cache.get(_identity(), [1])

    assert digest not in cache._blocks


def test_tenant_quota_rejects_oversized_admission() -> None:
    cache = HyperKVCache(CachePolicy(max_bytes=8192), tenant_quotas={"tiny": 2})

    result = cache.put(
        _identity(),
        [1],
        b"abcdef",
        context=AdmissionContext(tenant="tiny"),
    )

    assert result is None


def test_rendezvous_routing_is_stable() -> None:
    router = RendezvousShardRouter(["c", "a", "b"])

    assert router.route("same") == router.route("same")
    assert set(router.rank("same")) == {"a", "b", "c"}


def test_autotune_reacts_to_memory_pressure() -> None:
    cache = HyperKVCache(
        CachePolicy(
            max_bytes=8192,
            hot_ratio=0.5,
            warm_ratio=0.35,
            min_admission_score=0.1,
        )
    )

    policy = cache.autotune(memory_pressure=0.95, observed_hit_rate=0.9)

    assert policy.hot_ratio == pytest.approx(0.45)
    assert policy.min_admission_score == pytest.approx(0.15)


def test_evolution_manifest_has_exactly_fifty_unique_steps() -> None:
    assert len(HYPER_KV_EVOLUTION) == 50
    assert len(set(HYPER_KV_EVOLUTION)) == 50
