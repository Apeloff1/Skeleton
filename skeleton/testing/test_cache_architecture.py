from __future__ import annotations

import pytest

from skeleton.storage.cas import (
    CachePolicy,
    DigestPolicy,
    GovernedContentCache,
    GovernedContentStore,
    StorageContractError,
)


def _authority() -> GovernedContentStore:
    return GovernedContentStore(
        digest_policy=DigestPolicy(
            current_algorithm="sha256",
            accepted_algorithms=("sha256", "sha512"),
        )
    )


def test_cache_cannot_be_the_sole_authoritative_copy() -> None:
    cache = GovernedContentCache(_authority())

    with pytest.raises(KeyError):
        cache.rebuild(
            tenant_id="tenant-a",
            namespace="retrieval",
            logical_id="missing",
            version=1,
            generation=0,
        )


def test_cache_key_binds_tenant_version_and_trust_context() -> None:
    store = _authority()
    store.put(
        tenant_id="tenant-a",
        logical_id="index",
        version=3,
        trust_context="verified",
        payload=b"index-v3",
    )
    cache = GovernedContentCache(
        store,
        policy=CachePolicy(ttl_generations=5, stale_behavior="miss"),
    )
    cache.rebuild(
        tenant_id="tenant-a",
        namespace="retrieval",
        logical_id="index",
        version=3,
        generation=10,
    )

    assert cache.get(
        tenant_id="tenant-a",
        namespace="retrieval",
        logical_id="index",
        version=3,
        trust_context="verified",
        generation=11,
    ) == b"index-v3"
    assert cache.get(
        tenant_id="tenant-a",
        namespace="retrieval",
        logical_id="index",
        version=3,
        trust_context="unverified",
        generation=11,
    ) is None
    assert cache.get(
        tenant_id="tenant-b",
        namespace="retrieval",
        logical_id="index",
        version=3,
        trust_context="verified",
        generation=11,
    ) is None


def test_stale_cache_misses_or_rebuilds_by_explicit_policy() -> None:
    store = _authority()
    store.put(
        tenant_id="tenant-a",
        logical_id="feature-card",
        version=1,
        trust_context="internal",
        payload=b"card",
    )
    miss_cache = GovernedContentCache(
        store,
        policy=CachePolicy(ttl_generations=0, stale_behavior="miss"),
    )
    miss_cache.rebuild(
        tenant_id="tenant-a",
        namespace="cards",
        logical_id="feature-card",
        version=1,
        generation=1,
    )
    assert miss_cache.get(
        tenant_id="tenant-a",
        namespace="cards",
        logical_id="feature-card",
        version=1,
        trust_context="internal",
        generation=2,
    ) is None

    rebuild_cache = GovernedContentCache(
        store,
        policy=CachePolicy(ttl_generations=0, stale_behavior="rebuild"),
    )
    rebuild_cache.rebuild(
        tenant_id="tenant-a",
        namespace="cards",
        logical_id="feature-card",
        version=1,
        generation=1,
    )
    assert rebuild_cache.get(
        tenant_id="tenant-a",
        namespace="cards",
        logical_id="feature-card",
        version=1,
        trust_context="internal",
        generation=2,
    ) == b"card"


def test_cache_is_bounded_and_rebuild_replaces_superseded_digest_identity() -> None:
    store = _authority()
    cache = GovernedContentCache(
        store,
        policy=CachePolicy(
            ttl_generations=10,
            stale_behavior="miss",
            max_entries=2,
        ),
    )
    for index in range(3):
        store.put(
            tenant_id="tenant-a",
            logical_id=f"object-{index}",
            version=1,
            trust_context="verified",
            payload=f"payload-{index}".encode(),
        )
        cache.rebuild(
            tenant_id="tenant-a",
            namespace="bounded",
            logical_id=f"object-{index}",
            version=1,
            generation=index,
        )

    assert len(cache._entries) == 2

    store.put(
        tenant_id="tenant-a",
        logical_id="migrated",
        version=1,
        trust_context="verified",
        payload=b"same",
    )
    first = cache.rebuild(
        tenant_id="tenant-a",
        namespace="bounded",
        logical_id="migrated",
        version=1,
        generation=3,
    )
    old_fingerprint = first.key.fingerprint()

    store.migrate_digest(
        tenant_id="tenant-a",
        logical_id="migrated",
        version=1,
        to_algorithm="sha512",
    )
    second = cache.rebuild(
        tenant_id="tenant-a",
        namespace="bounded",
        logical_id="migrated",
        version=1,
        generation=4,
    )

    assert second.key.fingerprint() != old_fingerprint
    assert old_fingerprint not in cache._entries
    assert len(cache._entries) <= 2


def test_cache_entry_limit_is_fail_closed() -> None:
    with pytest.raises(StorageContractError, match="max_entries"):
        CachePolicy(max_entries=0)


def test_digest_migration_invalidates_old_cache_identity() -> None:
    store = _authority()
    store.put(
        tenant_id="tenant-a",
        logical_id="weights",
        version=2,
        trust_context="verified",
        payload=b"weights",
    )
    cache = GovernedContentCache(
        store,
        policy=CachePolicy(ttl_generations=10, stale_behavior="miss"),
    )
    cache.rebuild(
        tenant_id="tenant-a",
        namespace="models",
        logical_id="weights",
        version=2,
        generation=1,
    )

    store.migrate_digest(
        tenant_id="tenant-a",
        logical_id="weights",
        version=2,
        to_algorithm="sha512",
    )

    assert cache.get(
        tenant_id="tenant-a",
        namespace="models",
        logical_id="weights",
        version=2,
        trust_context="verified",
        generation=2,
    ) is None
    cache.rebuild(
        tenant_id="tenant-a",
        namespace="models",
        logical_id="weights",
        version=2,
        generation=2,
    )
    assert cache.get(
        tenant_id="tenant-a",
        namespace="models",
        logical_id="weights",
        version=2,
        trust_context="verified",
        generation=3,
    ) == b"weights"
