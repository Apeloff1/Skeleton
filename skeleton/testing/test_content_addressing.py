from __future__ import annotations

import pytest

from skeleton.storage.cas import (
    ContentDigest,
    DigestPolicy,
    GovernedContentStore,
    StorageContractError,
)


def test_canonical_json_content_has_stable_address() -> None:
    store = GovernedContentStore()
    left = store.put(
        tenant_id="tenant-a",
        logical_id="dataset-manifest",
        version=1,
        trust_context="verified",
        payload={"b": 2, "a": 1},
    )
    right_store = GovernedContentStore()
    right = right_store.put(
        tenant_id="tenant-a",
        logical_id="dataset-manifest",
        version=1,
        trust_context="verified",
        payload={"a": 1, "b": 2},
    )

    assert left.digest == right.digest
    assert left.digest.algorithm == "sha256"
    assert left.size_bytes == right.size_bytes


def test_logical_identity_version_cannot_be_rebound() -> None:
    store = GovernedContentStore()
    store.put(
        tenant_id="tenant-a",
        logical_id="checkpoint",
        version=1,
        trust_context="training",
        payload=b"first",
    )

    with pytest.raises(StorageContractError, match="cannot be rebound"):
        store.put(
            tenant_id="tenant-a",
            logical_id="checkpoint",
            version=1,
            trust_context="training",
            payload=b"second",
        )


def test_digest_migration_preserves_logical_identity_and_old_address() -> None:
    store = GovernedContentStore(
        digest_policy=DigestPolicy(
            current_algorithm="sha256",
            accepted_algorithms=("sha256", "sha512"),
        )
    )
    original = store.put(
        tenant_id="tenant-a",
        logical_id="model-artifact",
        version=7,
        trust_context="promotion-approved",
        payload=b"model-bytes",
    )

    migrated = store.migrate_digest(
        tenant_id="tenant-a",
        logical_id="model-artifact",
        version=7,
        to_algorithm="sha512",
    )

    assert migrated.logical_id == original.logical_id
    assert migrated.version == original.version
    assert migrated.digest.algorithm == "sha512"
    assert migrated.digest != original.digest

    by_old, old_payload = store.resolve(
        tenant_id="tenant-a",
        digest=original.digest,
    )
    by_new, new_payload = store.resolve(
        tenant_id="tenant-a",
        digest=migrated.digest,
    )
    assert by_old.logical_id == by_new.logical_id == "model-artifact"
    assert by_old.digest == by_new.digest == migrated.digest
    assert old_payload == new_payload == b"model-bytes"

    replay = store.put(
        tenant_id="tenant-a",
        logical_id="model-artifact",
        version=7,
        trust_context="promotion-approved",
        payload=b"model-bytes",
    )
    assert replay.digest == migrated.digest


def test_content_addresses_are_tenant_scoped() -> None:
    store = GovernedContentStore()
    obj = store.put(
        tenant_id="tenant-a",
        logical_id="artifact",
        version=1,
        trust_context="internal",
        payload=b"same-content",
    )

    with pytest.raises(KeyError):
        store.resolve(
            tenant_id="tenant-b",
            digest=obj.digest,
        )


def test_same_content_may_back_multiple_logical_ids_but_digest_only_resolution_is_ambiguous() -> None:
    store = GovernedContentStore()
    first = store.put(
        tenant_id="tenant-a",
        logical_id="artifact-a",
        version=1,
        trust_context="internal",
        payload=b"shared",
    )
    second = store.put(
        tenant_id="tenant-a",
        logical_id="artifact-b",
        version=1,
        trust_context="restricted",
        payload=b"shared",
    )

    assert first.digest == second.digest
    with pytest.raises(StorageContractError, match="ambiguous"):
        store.resolve(
            tenant_id="tenant-a",
            digest=first.digest,
        )


def test_unaccepted_digest_algorithm_fails_closed() -> None:
    store = GovernedContentStore(
        digest_policy=DigestPolicy(
            current_algorithm="sha256",
            accepted_algorithms=("sha256",),
        )
    )
    value = "0" * 128
    with pytest.raises(StorageContractError, match="not accepted"):
        store.resolve(
            tenant_id="tenant-a",
            digest=ContentDigest("sha512", value),
        )
