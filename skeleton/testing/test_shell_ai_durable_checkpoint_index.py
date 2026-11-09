"""Repairable exact durable-checkpoint lookup index tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import (
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpoint,
    DurableChainCheckpointStore,
    DurableCheckpointError,
    DurableCheckpointLookupIndex,
    SignedDurableChainCheckpoint,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceNode,
)


GENESIS = "0" * 64


def signer():
    return ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )


def fixture():
    backend = InMemoryFencedStore()
    source = ContentAddressedEvidenceChain(
        backend,
        namespace="source",
        max_events=100,
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        max_checkpoints=100,
        clock=lambda: 50.0,
    )
    return backend, source, checkpoints


def append_source(source, count, *, start=0):
    return tuple(
        source.append(
            "source.event",
            {"index": index},
        )
        for index in range(start, start + count)
    )


def publish_after_append(
    source,
    checkpoints,
    *,
    chain_id="source",
    index=0,
):
    source.append(
        "source.event",
        {"index": index},
    )
    return checkpoints.publish(
        chain_id,
        source,
    )


def test_publish_creates_digest_lookup():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    key = checkpoints._digest_lookup_key(
        item.checkpoint.digest
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    assert record is not None
    lookup = checkpoints._lookup(
        dict(record.value)
    )
    assert lookup.checkpoint_digest == (
        item.checkpoint.digest
    )
    assert lookup.chain_node_hash == (
        item.chain_node_hash
    )


def test_publish_creates_root_lookup():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    key = checkpoints._root_lookup_key(
        "source",
        item.checkpoint.root_hash,
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    assert record is not None
    lookup = checkpoints._lookup(
        dict(record.value)
    )
    assert lookup.chain_id == "source"
    assert lookup.root_hash == (
        item.checkpoint.root_hash
    )


def test_find_by_digest_round_trip():
    _, source, checkpoints = fixture()
    append_source(source, 2)
    item = checkpoints.publish(
        "source",
        source,
    )
    assert checkpoints.find_by_digest(
        item.checkpoint.digest
    ) == item


def test_find_by_root_round_trip():
    _, source, checkpoints = fixture()
    append_source(source, 2)
    item = checkpoints.publish(
        "source",
        source,
    )
    assert checkpoints.find_by_root(
        "source",
        item.checkpoint.root_hash,
    ) == item


def test_fresh_checkpoint_store_reads_existing_indexes():
    backend, source, checkpoints = fixture()
    append_source(source, 2)
    item = checkpoints.publish(
        "source",
        source,
    )
    fresh = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        max_checkpoints=100,
        clock=lambda: 60.0,
    )
    assert fresh.find_by_digest(
        item.checkpoint.digest
    ) == item
    assert fresh.find_by_root(
        "source",
        item.checkpoint.root_hash,
    ) == item


def test_missing_digest_index_self_heals_from_canonical_registry():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    key = checkpoints._digest_lookup_key(
        item.checkpoint.digest
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.delete(
        "checkpoints",
        key,
        expected_revision=record.revision,
    )
    assert backend.get(
        "checkpoints",
        key,
    ) is None

    assert checkpoints.find_by_digest(
        item.checkpoint.digest
    ) == item
    assert backend.get(
        "checkpoints",
        key,
    ) is not None


def test_missing_root_index_self_heals_from_canonical_registry():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    key = checkpoints._root_lookup_key(
        "source",
        item.checkpoint.root_hash,
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.delete(
        "checkpoints",
        key,
        expected_revision=record.revision,
    )
    assert checkpoints.find_by_root(
        "source",
        item.checkpoint.root_hash,
    ) == item
    assert backend.get(
        "checkpoints",
        key,
    ) is not None


def test_idempotent_publish_repairs_missing_indexes():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    first = checkpoints.publish(
        "source",
        source,
    )
    for key in (
        checkpoints._digest_lookup_key(
            first.checkpoint.digest
        ),
        checkpoints._root_lookup_key(
            "source",
            first.checkpoint.root_hash,
        ),
    ):
        record = backend.get(
            "checkpoints",
            key,
        )
        backend.delete(
            "checkpoints",
            key,
            expected_revision=record.revision,
        )

    second = checkpoints.publish(
        "source",
        source,
    )
    assert second == first
    assert checkpoints.find_by_digest(
        first.checkpoint.digest
    ) == first
    assert checkpoints.find_by_root(
        "source",
        first.checkpoint.root_hash,
    ) == first


def test_repair_lookup_indexes_backfills_all_checkpoints():
    backend, source, checkpoints = fixture()
    first = publish_after_append(
        source,
        checkpoints,
        index=1,
    )
    second = publish_after_append(
        source,
        checkpoints,
        index=2,
    )
    third = publish_after_append(
        source,
        checkpoints,
        index=3,
    )
    for item in (
        first,
        second,
        third,
    ):
        for key in (
            checkpoints._digest_lookup_key(
                item.checkpoint.digest
            ),
            checkpoints._root_lookup_key(
                "source",
                item.checkpoint.root_hash,
            ),
        ):
            record = backend.get(
                "checkpoints",
                key,
            )
            backend.delete(
                "checkpoints",
                key,
                expected_revision=record.revision,
            )

    repaired = (
        checkpoints
        .repair_lookup_indexes()
    )
    assert repaired == 6
    assert checkpoints.verify_lookup_indexes()


def test_repair_is_idempotent():
    _, source, checkpoints = fixture()
    publish_after_append(
        source,
        checkpoints,
        index=1,
    )
    publish_after_append(
        source,
        checkpoints,
        index=2,
    )
    assert checkpoints.repair_lookup_indexes() == 0
    assert checkpoints.repair_lookup_indexes() == 0


def test_verify_lookup_indexes_true_for_healthy_registry():
    _, source, checkpoints = fixture()
    for index in range(4):
        publish_after_append(
            source,
            checkpoints,
            index=index,
        )
    assert checkpoints.verify()
    assert checkpoints.verify_lookup_indexes()


def test_find_missing_digest_returns_none():
    _, _, checkpoints = fixture()
    assert checkpoints.find_by_digest(
        "f" * 64
    ) is None


def test_find_missing_root_returns_none():
    _, _, checkpoints = fixture()
    assert checkpoints.find_by_root(
        "source",
        "f" * 64,
    ) is None


@pytest.mark.parametrize(
    "digest",
    ["", "bad", "a" * 63, "a" * 65],
)
def test_find_by_digest_validates_digest(digest):
    _, _, checkpoints = fixture()
    with pytest.raises(ValueError):
        checkpoints.find_by_digest(
            digest
        )


@pytest.mark.parametrize(
    "root",
    ["", "bad", "a" * 63, "a" * 65],
)
def test_find_by_root_validates_root(root):
    _, _, checkpoints = fixture()
    with pytest.raises(ValueError):
        checkpoints.find_by_root(
            "source",
            root,
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 129],
)
def test_find_by_root_validates_chain_id(chain_id):
    _, _, checkpoints = fixture()
    with pytest.raises(ValueError):
        checkpoints.find_by_root(
            chain_id,
            "a" * 64,
        )


def test_root_lookup_is_chain_scoped_for_same_genesis_root():
    backend = InMemoryFencedStore()
    source_a = ContentAddressedEvidenceChain(
        backend,
        namespace="source-a",
    )
    source_b = ContentAddressedEvidenceChain(
        backend,
        namespace="source-b",
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 50.0,
    )
    checkpoint_a = checkpoints.publish(
        "a",
        source_a,
    )
    checkpoint_b = checkpoints.publish(
        "b",
        source_b,
    )
    assert checkpoint_a.checkpoint.root_hash == GENESIS
    assert checkpoint_b.checkpoint.root_hash == GENESIS
    assert checkpoint_a.checkpoint.digest != (
        checkpoint_b.checkpoint.digest
    )
    assert checkpoints.find_by_root(
        "a",
        GENESIS,
    ) == checkpoint_a
    assert checkpoints.find_by_root(
        "b",
        GENESIS,
    ) == checkpoint_b


def test_digest_lookup_is_global_because_checkpoint_digest_binds_chain():
    backend = InMemoryFencedStore()
    source_a = ContentAddressedEvidenceChain(
        backend,
        namespace="source-a",
    )
    source_b = ContentAddressedEvidenceChain(
        backend,
        namespace="source-b",
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 50.0,
    )
    a = checkpoints.publish(
        "a",
        source_a,
    )
    b = checkpoints.publish(
        "b",
        source_b,
    )
    assert checkpoints.find_by_digest(
        a.checkpoint.digest
    ) == a
    assert checkpoints.find_by_digest(
        b.checkpoint.digest
    ) == b


def test_lookup_model_round_trip():
    lookup = DurableCheckpointLookupIndex(
        "chain",
        3,
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )
    assert lookup.to_dict() == {
        "chain_id": "chain",
        "sequence": 3,
        "root_hash": "a" * 64,
        "checkpoint_digest": "b" * 64,
        "chain_node_hash": "c" * 64,
    }


@pytest.mark.parametrize(
    "args",
    [
        ("", 0, "a" * 64, "b" * 64, "c" * 64),
        ("chain", -1, "a" * 64, "b" * 64, "c" * 64),
        ("chain", True, "a" * 64, "b" * 64, "c" * 64),
        ("chain", 0, "bad", "b" * 64, "c" * 64),
        ("chain", 0, "a" * 64, "bad", "c" * 64),
        ("chain", 0, "a" * 64, "b" * 64, "bad"),
    ],
)
def test_lookup_model_validation(args):
    with pytest.raises(ValueError):
        DurableCheckpointLookupIndex(
            *args
        )


def test_corrupt_digest_lookup_type_fails_closed():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    key = checkpoints._digest_lookup_key(
        item.checkpoint.digest
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.compare_and_swap(
        "checkpoints",
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(
        (DurableCheckpointError, KeyError),
    ):
        checkpoints.find_by_digest(
            item.checkpoint.digest
        )


def test_corrupt_root_lookup_type_fails_closed():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    key = checkpoints._root_lookup_key(
        "source",
        item.checkpoint.root_hash,
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.compare_and_swap(
        "checkpoints",
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(
        (DurableCheckpointError, KeyError),
    ):
        checkpoints.find_by_root(
            "source",
            item.checkpoint.root_hash,
        )


def test_digest_index_pointing_to_other_checkpoint_is_rejected():
    backend, source, checkpoints = fixture()
    first = publish_after_append(
        source,
        checkpoints,
        index=1,
    )
    second = publish_after_append(
        source,
        checkpoints,
        index=2,
    )
    key = checkpoints._digest_lookup_key(
        first.checkpoint.digest
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.compare_and_swap(
        "checkpoints",
        key,
        expected_revision=record.revision,
        value=checkpoints._lookup_for(
            second
        ).to_dict(),
    )
    with pytest.raises(
        DurableCheckpointError,
        match="differs",
    ):
        checkpoints.find_by_digest(
            first.checkpoint.digest
        )


def test_root_index_pointing_to_other_checkpoint_is_rejected():
    backend, source, checkpoints = fixture()
    first = publish_after_append(
        source,
        checkpoints,
        index=1,
    )
    second = publish_after_append(
        source,
        checkpoints,
        index=2,
    )
    key = checkpoints._root_lookup_key(
        "source",
        first.checkpoint.root_hash,
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.compare_and_swap(
        "checkpoints",
        key,
        expected_revision=record.revision,
        value=checkpoints._lookup_for(
            second
        ).to_dict(),
    )
    with pytest.raises(
        DurableCheckpointError,
        match="differs",
    ):
        checkpoints.find_by_root(
            "source",
            first.checkpoint.root_hash,
        )


def test_lookup_chain_node_kind_substitution_is_rejected():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    lookup = checkpoints._lookup_for(
        item
    )
    foreign = checkpoints._chain.append(
        "foreign.kind",
        {"value": 1},
    )
    tampered = replace(
        lookup,
        chain_node_hash=foreign.node_hash,
    )
    key = checkpoints._digest_lookup_key(
        item.checkpoint.digest
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.compare_and_swap(
        "checkpoints",
        key,
        expected_revision=record.revision,
        value=tampered.to_dict(),
    )
    with pytest.raises(
        DurableCheckpointError,
        match="wrong kind",
    ):
        checkpoints.find_by_digest(
            item.checkpoint.digest
        )


def test_orphan_signed_checkpoint_node_is_rejected():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    head = source.head()
    checkpoint = DurableChainCheckpoint(
        1,
        "source",
        head.sequence,
        head.root_hash,
        "",
        75.0,
    )
    signature = checkpoints.signer.sign(
        "durable-chain-checkpoint",
        checkpoint.digest,
        metadata={
            "chain_id": "source",
            "sequence": head.sequence,
        },
    )
    payload = {
        "checkpoint": checkpoint.to_dict(),
        "signature": signature.to_dict(),
    }
    current_registry_head = (
        checkpoints._chain.head()
    )
    orphan_hash = (
        ContentAddressedEvidenceChain
        .node_digest(
            current_registry_head.root_hash,
            current_registry_head.sequence + 1,
            "durable.chain.checkpoint",
            payload,
        )
    )
    orphan_node = EvidenceNode(
        current_registry_head.sequence + 1,
        current_registry_head.root_hash,
        orphan_hash,
        "durable.chain.checkpoint",
        payload,
    )
    backend.put_if_absent(
        "checkpoints",
        f"node:{orphan_hash}",
        orphan_node,
    )
    orphan_item = SignedDurableChainCheckpoint(
        checkpoint,
        signature,
        orphan_hash,
    )
    lookup = checkpoints._lookup_for(
        orphan_item
    )
    backend.put_if_absent(
        "checkpoints",
        checkpoints._digest_lookup_key(
            checkpoint.digest
        ),
        lookup.to_dict(),
    )
    with pytest.raises(
        DurableCheckpointError,
        match="not committed",
    ):
        checkpoints.find_by_digest(
            checkpoint.digest
        )


def test_lookup_rejects_registry_node_payload_tamper():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    key = f"node:{item.chain_node_hash}"
    record = backend.get(
        "checkpoints",
        key,
    )
    node = record.value
    payload = dict(node.payload)
    raw_checkpoint = dict(
        payload["checkpoint"]
    )
    raw_checkpoint["sequence"] = 999
    payload["checkpoint"] = raw_checkpoint
    backend.compare_and_swap(
        "checkpoints",
        key,
        expected_revision=record.revision,
        value=replace(
            node,
            payload=payload,
        ),
    )
    with pytest.raises(
        DurableCheckpointError,
        match="unavailable",
    ):
        checkpoints.find_by_digest(
            item.checkpoint.digest
        )


def test_verify_lookup_indexes_false_after_index_substitution():
    backend, source, checkpoints = fixture()
    first = publish_after_append(
        source,
        checkpoints,
        index=1,
    )
    second = publish_after_append(
        source,
        checkpoints,
        index=2,
    )
    key = checkpoints._digest_lookup_key(
        first.checkpoint.digest
    )
    record = backend.get(
        "checkpoints",
        key,
    )
    backend.compare_and_swap(
        "checkpoints",
        key,
        expected_revision=record.revision,
        value=checkpoints._lookup_for(
            second
        ).to_dict(),
    )
    assert not checkpoints.verify_lookup_indexes()


def test_repair_fails_when_canonical_registry_is_corrupt():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    node_key = f"node:{item.chain_node_hash}"
    record = backend.get(
        "checkpoints",
        node_key,
    )
    backend.compare_and_swap(
        "checkpoints",
        node_key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            kind="wrong.kind",
        ),
    )
    assert not checkpoints.verify()
    with pytest.raises(
        DurableCheckpointError,
        match="invalid checkpoint registry",
    ):
        checkpoints.repair_lookup_indexes()


def test_root_lookup_key_is_deterministic_and_chain_scoped():
    _, _, checkpoints = fixture()
    a = checkpoints._root_lookup_key(
        "a",
        "f" * 64,
    )
    a_again = checkpoints._root_lookup_key(
        "a",
        "f" * 64,
    )
    b = checkpoints._root_lookup_key(
        "b",
        "f" * 64,
    )
    assert a == a_again
    assert a != b
    assert a.startswith(
        "checkpoint-root:"
    )


def test_digest_lookup_key_contains_digest_identity():
    _, _, checkpoints = fixture()
    digest = "f" * 64
    key = checkpoints._digest_lookup_key(
        digest
    )
    assert key == (
        "checkpoint-digest:"
        + digest
    )


def test_index_survives_later_checkpoint_publication():
    _, source, checkpoints = fixture()
    first = publish_after_append(
        source,
        checkpoints,
        index=1,
    )
    second = publish_after_append(
        source,
        checkpoints,
        index=2,
    )
    third = publish_after_append(
        source,
        checkpoints,
        index=3,
    )
    assert checkpoints.find_by_digest(
        first.checkpoint.digest
    ) == first
    assert checkpoints.find_by_root(
        "source",
        first.checkpoint.root_hash,
    ) == first
    assert checkpoints.find_by_digest(
        second.checkpoint.digest
    ) == second
    assert checkpoints.find_by_digest(
        third.checkpoint.digest
    ) == third


def test_indexes_cover_multiple_checkpoint_chains():
    backend = InMemoryFencedStore()
    source_a = ContentAddressedEvidenceChain(
        backend,
        namespace="source-a",
    )
    source_b = ContentAddressedEvidenceChain(
        backend,
        namespace="source-b",
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 50.0,
    )
    append_source(source_a, 1)
    append_source(source_b, 2)
    a = checkpoints.publish(
        "a",
        source_a,
    )
    b = checkpoints.publish(
        "b",
        source_b,
    )
    assert checkpoints.find_by_root(
        "a",
        a.checkpoint.root_hash,
    ) == a
    assert checkpoints.find_by_root(
        "b",
        b.checkpoint.root_hash,
    ) == b
    assert checkpoints.verify_lookup_indexes()


def test_find_by_root_wrong_chain_does_not_return_other_chain_checkpoint():
    backend = InMemoryFencedStore()
    source = ContentAddressedEvidenceChain(
        backend,
        namespace="source",
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 50.0,
    )
    append_source(source, 1)
    item = checkpoints.publish(
        "a",
        source,
    )
    assert checkpoints.find_by_root(
        "b",
        item.checkpoint.root_hash,
    ) is None


def test_lookup_index_is_repaired_by_fresh_store():
    backend, source, checkpoints = fixture()
    append_source(source, 2)
    item = checkpoints.publish(
        "source",
        source,
    )
    digest_key = checkpoints._digest_lookup_key(
        item.checkpoint.digest
    )
    root_key = checkpoints._root_lookup_key(
        "source",
        item.checkpoint.root_hash,
    )
    for key in (digest_key, root_key):
        record = backend.get(
            "checkpoints",
            key,
        )
        backend.delete(
            "checkpoints",
            key,
            expected_revision=record.revision,
        )

    fresh = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 99.0,
    )
    assert fresh.find_by_digest(
        item.checkpoint.digest
    ) == item
    assert fresh.find_by_root(
        "source",
        item.checkpoint.root_hash,
    ) == item
    assert backend.get(
        "checkpoints",
        digest_key,
    ) is not None
    assert backend.get(
        "checkpoints",
        root_key,
    ) is not None


def test_empty_source_genesis_checkpoint_is_indexed():
    _, source, checkpoints = fixture()
    item = checkpoints.publish(
        "source",
        source,
    )
    assert item.checkpoint.sequence == 0
    assert item.checkpoint.root_hash == GENESIS
    assert checkpoints.find_by_root(
        "source",
        GENESIS,
    ) == item
    assert checkpoints.find_by_digest(
        item.checkpoint.digest
    ) == item


def test_lookup_for_preserves_exact_checkpoint_identity():
    _, source, checkpoints = fixture()
    append_source(source, 3)
    item = checkpoints.publish(
        "source",
        source,
    )
    lookup = checkpoints._lookup_for(
        item
    )
    assert lookup.chain_id == (
        item.checkpoint.chain_id
    )
    assert lookup.sequence == (
        item.checkpoint.sequence
    )
    assert lookup.root_hash == (
        item.checkpoint.root_hash
    )
    assert lookup.checkpoint_digest == (
        item.checkpoint.digest
    )
    assert lookup.chain_node_hash == (
        item.chain_node_hash
    )


def test_find_by_digest_validates_checkpoint_signature():
    backend, source, checkpoints = fixture()
    append_source(source, 1)
    item = checkpoints.publish(
        "source",
        source,
    )
    node_key = f"node:{item.chain_node_hash}"
    record = backend.get(
        "checkpoints",
        node_key,
    )
    node = record.value
    payload = dict(node.payload)
    signature = dict(
        payload["signature"]
    )
    signature["signature"] = "0" * 64
    payload["signature"] = signature
    # The outer content hash intentionally becomes invalid too; exact lookup
    # must fail closed before trusting either layer.
    backend.compare_and_swap(
        "checkpoints",
        node_key,
        expected_revision=record.revision,
        value=replace(
            node,
            payload=payload,
        ),
    )
    with pytest.raises(
        DurableCheckpointError,
    ):
        checkpoints.find_by_digest(
            item.checkpoint.digest
        )
