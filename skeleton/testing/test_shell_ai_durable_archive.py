"""Signed durable archive manifest regression and adversarial tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import (
    DurableArchiveEntry,
    DurableArchiveError,
    DurableArchiveManifest,
    DurableArchiveManifestBuilder,
    DurableArchiveVerification,
    SignedDurableArchiveManifest,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def checkpoint_signer() -> ArtifactSigner:
    return ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )


def archive_signer() -> ArtifactSigner:
    return ArtifactSigner(
        "archive",
        b"a" * 32,
        clock=lambda: 200.0,
    )


def journal_fixture(
    *,
    max_events=100,
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=max_events,
        clock=lambda: 10.0,
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer(),
        clock=lambda: 200.0,
    )
    return backend, journal, checkpoints, builder


def append_events(
    journal: DistributedAIDecisionJournal,
    count: int,
):
    result = []
    for index in range(count):
        result.append(
            journal.append(
                "archive.event",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
            )
        )
    return tuple(result)


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(f"receipt:{index}"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


def test_build_empty_journal_archive():
    _, journal, checkpoints, builder = journal_fixture()
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    manifest = archive.manifest
    assert manifest.node_count == 0
    assert manifest.checkpoint_sequence == 0
    assert manifest.entries == ()
    assert manifest.checkpoint_root == "0" * 64
    assert len(manifest.archive_id) == 64
    assert archive.signature.artifact_type == (
        "durable-archive-manifest"
    )
    assert (
        archive.signature.artifact_digest
        == manifest.digest
    )
    assert builder.require(
        archive,
        checkpoint,
        journal,
    ).valid


def test_build_nonempty_journal_archive():
    _, journal, checkpoints, builder = journal_fixture()
    events = append_events(
        journal,
        3,
    )
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    manifest = archive.manifest
    assert manifest.node_count == 3
    assert manifest.checkpoint_sequence == 3
    assert tuple(
        item.node_hash
        for item in manifest.entries
    ) == tuple(
        item.event_hash
        for item in events
    )
    assert tuple(
        item.kind
        for item in manifest.entries
    ) == (
        "archive.event",
        "archive.event",
        "archive.event",
    )
    assert (
        manifest.entries[-1].node_hash
        == checkpoint.checkpoint.root_hash
    )
    assert builder.require(
        archive,
        checkpoint,
        journal,
    ).valid


def test_archive_id_is_deterministic_for_checkpoint():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    first = builder.build(
        checkpoint,
        journal,
    )
    second = builder.build(
        checkpoint,
        journal,
    )
    assert (
        first.manifest.archive_id
        == second.manifest.archive_id
    )
    assert (
        first.manifest.archive_id
        == DurableArchiveManifest.derive_archive_id(
            "journal",
            checkpoint.checkpoint.digest,
        )
    )


def test_archive_manifest_digest_is_deterministic_at_fixed_clock():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    first = builder.build(
        checkpoint,
        journal,
    )
    second = builder.build(
        checkpoint,
        journal,
    )
    assert first.manifest.digest == second.manifest.digest
    assert first.signature.signature == second.signature.signature


def test_archive_remains_valid_after_journal_advances():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    append_events(journal, 3)
    report = builder.require(
        archive,
        checkpoint,
        journal,
    )
    assert report.valid
    assert report.committed_ancestor
    assert report.current_sequence == 5
    assert (
        report.current_root
        == journal.root_hash()
    )
    assert (
        report.checkpoint_root
        != report.current_root
    )


def test_archive_prefix_excludes_later_events():
    _, journal, checkpoints, builder = journal_fixture()
    first_events = append_events(
        journal,
        2,
    )
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    append_events(journal, 2)
    assert tuple(
        item.node_hash
        for item in archive.manifest.entries
    ) == tuple(
        item.event_hash
        for item in first_events
    )


def test_build_receipt_archive():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=100,
    )
    for index in range(3):
        receipts.append(
            receipt(index)
        )
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    checkpoint = checkpoints.publish(
        "receipts",
        receipts,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer(),
        clock=lambda: 200.0,
    )
    archive = builder.build(
        checkpoint,
        receipts,
    )
    assert archive.manifest.node_count == 3
    assert all(
        item.kind == "execution.receipt"
        for item in archive.manifest.entries
    )
    assert tuple(
        item.object_digest
        for item in archive.manifest.entries
    ) == tuple(
        receipt(index).fingerprint
        for index in range(3)
    )
    assert builder.require(
        archive,
        checkpoint,
        receipts,
    ).valid


def test_receipt_archive_survives_later_receipts():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    receipts.append(receipt(0))
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
        namespace="checkpoints",
    )
    checkpoint = checkpoints.publish(
        "receipts",
        receipts,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer(),
        clock=lambda: 200.0,
    )
    archive = builder.build(
        checkpoint,
        receipts,
    )
    receipts.append(receipt(1))
    report = builder.require(
        archive,
        checkpoint,
        receipts,
    )
    assert report.valid
    assert report.current_sequence == 2
    assert report.node_count == 1


def test_fresh_builder_verifies_existing_archive():
    backend, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 3)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    fresh_checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
        namespace="checkpoints",
    )
    fresh = DurableArchiveManifestBuilder(
        fresh_checkpoints,
        archive_signer(),
        clock=lambda: 999.0,
    )
    assert fresh.require(
        archive,
        checkpoint,
        journal,
    ).valid


def test_archive_signature_tamper_is_rejected():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    tampered = replace(
        archive,
        signature=replace(
            archive.signature,
            signature=fp("tampered"),
        ),
    )
    report = builder.inspect(
        tampered,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert any(
        "signature is invalid" in reason
        for reason in report.reasons
    )


def test_archive_wrong_artifact_type_is_rejected():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    tampered = replace(
        archive,
        signature=replace(
            archive.signature,
            artifact_type="wrong",
        ),
    )
    report = builder.inspect(
        tampered,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert any(
        "artifact type" in reason
        for reason in report.reasons
    )


def test_archive_signature_digest_substitution_is_rejected():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    tampered = replace(
        archive,
        signature=replace(
            archive.signature,
            artifact_digest=fp("other"),
        ),
    )
    report = builder.inspect(
        tampered,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert any(
        "signature digest" in reason
        for reason in report.reasons
    )


def test_archive_chain_id_substitution_is_rejected():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    tampered_manifest = replace(
        archive.manifest,
        chain_id="other",
    )
    tampered_signature = builder.signer.sign(
        "durable-archive-manifest",
        tampered_manifest.digest,
    )
    tampered = SignedDurableArchiveManifest(
        tampered_manifest,
        tampered_signature,
    )
    report = builder.inspect(
        tampered,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert any(
        "chain_id differs" in reason
        for reason in report.reasons
    )


def test_archive_checkpoint_digest_substitution_is_rejected():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    manifest = replace(
        archive.manifest,
        checkpoint_digest=fp("other"),
    )
    signed = SignedDurableArchiveManifest(
        manifest,
        builder.signer.sign(
            "durable-archive-manifest",
            manifest.digest,
        ),
    )
    report = builder.inspect(
        signed,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert any(
        "checkpoint digest differs" in reason
        for reason in report.reasons
    )


def test_archive_entries_substitution_is_rejected():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    entries = list(
        archive.manifest.entries
    )
    entries[0] = replace(
        entries[0],
        kind="substituted.kind",
    )
    entries_tuple = tuple(entries)
    manifest = replace(
        archive.manifest,
        entries=entries_tuple,
        entries_digest=(
            DurableArchiveManifest.compute_entries_digest(
                entries_tuple
            )
        ),
    )
    signed = SignedDurableArchiveManifest(
        manifest,
        builder.signer.sign(
            "durable-archive-manifest",
            manifest.digest,
        ),
    )
    report = builder.inspect(
        signed,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert any(
        "entries differ" in reason
        for reason in report.reasons
    )


def test_archive_checkpoint_must_be_canonical():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    forged = replace(
        checkpoint,
        chain_node_hash=fp("uncommitted"),
    )
    with pytest.raises(
        DurableArchiveError,
    ):
        builder.build(
            forged,
            journal,
        )


def test_builder_entry_bound_is_enforced():
    backend, journal, checkpoints, _ = journal_fixture()
    append_events(journal, 3)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer(),
        max_entries=2,
    )
    with pytest.raises(
        DurableArchiveError,
        match="bound",
    ):
        builder.build(
            checkpoint,
            journal,
        )


@pytest.mark.parametrize(
    "max_entries",
    [0, -1, True],
)
def test_builder_entry_bound_validation(max_entries):
    _, _, checkpoints, _ = journal_fixture()
    with pytest.raises(ValueError, match="max_entries"):
        DurableArchiveManifestBuilder(
            checkpoints,
            archive_signer(),
            max_entries=max_entries,
        )


def test_builder_constructor_type_validation():
    _, _, checkpoints, _ = journal_fixture()
    with pytest.raises(TypeError, match="checkpoints"):
        DurableArchiveManifestBuilder(
            object(),
            archive_signer(),
        )
    with pytest.raises(TypeError, match="signer"):
        DurableArchiveManifestBuilder(
            checkpoints,
            object(),
        )
    with pytest.raises(TypeError, match="clock"):
        DurableArchiveManifestBuilder(
            checkpoints,
            archive_signer(),
            clock=object(),
        )


def test_build_checkpoint_type_validation():
    _, journal, _, builder = journal_fixture()
    with pytest.raises(TypeError, match="checkpoint"):
        builder.build(
            object(),
            journal,
        )


def test_inspect_item_type_validation():
    _, journal, checkpoints, builder = journal_fixture()
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    with pytest.raises(TypeError, match="item"):
        builder.inspect(
            object(),
            checkpoint,
            journal,
        )


def test_inspect_checkpoint_type_validation():
    _, journal, checkpoints, builder = journal_fixture()
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    with pytest.raises(TypeError, match="checkpoint"):
        builder.inspect(
            archive,
            object(),
            journal,
        )


def test_require_raises_for_invalid_archive():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    tampered = replace(
        archive,
        signature=replace(
            archive.signature,
            signature=fp("tampered"),
        ),
    )
    with pytest.raises(
        DurableArchiveError,
    ):
        builder.require(
            tampered,
            checkpoint,
            journal,
        )


def test_archive_entry_validation():
    with pytest.raises(ValueError):
        DurableArchiveEntry(
            0,
            "0" * 64,
            fp("node"),
            "kind",
            fp("object"),
        )
    with pytest.raises(ValueError):
        DurableArchiveEntry(
            1,
            "bad",
            fp("node"),
            "kind",
            fp("object"),
        )
    with pytest.raises(ValueError):
        DurableArchiveEntry(
            1,
            "0" * 64,
            "bad",
            "kind",
            fp("object"),
        )
    with pytest.raises(ValueError):
        DurableArchiveEntry(
            1,
            "0" * 64,
            fp("node"),
            "",
            fp("object"),
        )
    with pytest.raises(ValueError):
        DurableArchiveEntry(
            1,
            "0" * 64,
            fp("node"),
            "kind",
            "bad",
        )


def test_archive_entry_to_dict():
    item = DurableArchiveEntry(
        1,
        "0" * 64,
        fp("node"),
        "kind",
        fp("object"),
    )
    assert item.to_dict() == {
        "sequence": 1,
        "previous_hash": "0" * 64,
        "node_hash": fp("node"),
        "kind": "kind",
        "object_digest": fp("object"),
    }


def test_manifest_rejects_wrong_schema():
    with pytest.raises(ValueError, match="schema"):
        DurableArchiveManifest(
            2,
            "archive",
            "chain",
            fp("checkpoint"),
            0,
            "0" * 64,
            0,
            DurableArchiveManifest.compute_entries_digest(
                ()
            ),
            (),
            1.0,
        )


def test_manifest_rejects_invalid_archive_id():
    with pytest.raises(ValueError, match="archive_id"):
        DurableArchiveManifest(
            1,
            "",
            "chain",
            fp("checkpoint"),
            0,
            "0" * 64,
            0,
            DurableArchiveManifest.compute_entries_digest(
                ()
            ),
            (),
            1.0,
        )


def test_manifest_rejects_count_mismatch():
    entry = DurableArchiveEntry(
        1,
        "0" * 64,
        fp("node"),
        "kind",
        fp("object"),
    )
    with pytest.raises(ValueError, match="node_count"):
        DurableArchiveManifest(
            1,
            "archive",
            "chain",
            fp("checkpoint"),
            1,
            entry.node_hash,
            0,
            DurableArchiveManifest.compute_entries_digest(
                (entry,)
            ),
            (entry,),
            1.0,
        )


def test_manifest_rejects_checkpoint_sequence_mismatch():
    entry = DurableArchiveEntry(
        1,
        "0" * 64,
        fp("node"),
        "kind",
        fp("object"),
    )
    with pytest.raises(ValueError, match="checkpoint sequence"):
        DurableArchiveManifest(
            1,
            "archive",
            "chain",
            fp("checkpoint"),
            2,
            entry.node_hash,
            1,
            DurableArchiveManifest.compute_entries_digest(
                (entry,)
            ),
            (entry,),
            1.0,
        )


def test_manifest_rejects_noncontiguous_sequence():
    first = DurableArchiveEntry(
        1,
        "0" * 64,
        fp("one"),
        "kind",
        fp("object-one"),
    )
    second = DurableArchiveEntry(
        3,
        first.node_hash,
        fp("two"),
        "kind",
        fp("object-two"),
    )
    with pytest.raises(ValueError, match="sequence"):
        DurableArchiveManifest(
            1,
            "archive",
            "chain",
            fp("checkpoint"),
            2,
            second.node_hash,
            2,
            DurableArchiveManifest.compute_entries_digest(
                (first, second)
            ),
            (first, second),
            1.0,
        )


def test_manifest_rejects_noncontiguous_hash():
    first = DurableArchiveEntry(
        1,
        "0" * 64,
        fp("one"),
        "kind",
        fp("object-one"),
    )
    second = DurableArchiveEntry(
        2,
        fp("wrong"),
        fp("two"),
        "kind",
        fp("object-two"),
    )
    with pytest.raises(ValueError, match="previous hash"):
        DurableArchiveManifest(
            1,
            "archive",
            "chain",
            fp("checkpoint"),
            2,
            second.node_hash,
            2,
            DurableArchiveManifest.compute_entries_digest(
                (first, second)
            ),
            (first, second),
            1.0,
        )


def test_manifest_rejects_wrong_terminal_root():
    first = DurableArchiveEntry(
        1,
        "0" * 64,
        fp("one"),
        "kind",
        fp("object"),
    )
    with pytest.raises(ValueError, match="terminate"):
        DurableArchiveManifest(
            1,
            "archive",
            "chain",
            fp("checkpoint"),
            1,
            fp("other"),
            1,
            DurableArchiveManifest.compute_entries_digest(
                (first,)
            ),
            (first,),
            1.0,
        )


def test_manifest_rejects_entries_digest_mismatch():
    with pytest.raises(ValueError, match="entries_digest"):
        DurableArchiveManifest(
            1,
            "archive",
            "chain",
            fp("checkpoint"),
            0,
            "0" * 64,
            0,
            fp("wrong"),
            (),
            1.0,
        )


def test_manifest_rejects_invalid_created_at():
    with pytest.raises(ValueError, match="created_at"):
        DurableArchiveManifest(
            1,
            "archive",
            "chain",
            fp("checkpoint"),
            0,
            "0" * 64,
            0,
            DurableArchiveManifest.compute_entries_digest(
                ()
            ),
            (),
            -1.0,
        )


def test_archive_id_changes_with_checkpoint():
    one = DurableArchiveManifest.derive_archive_id(
        "chain",
        fp("one"),
    )
    two = DurableArchiveManifest.derive_archive_id(
        "chain",
        fp("two"),
    )
    assert one != two


def test_archive_id_changes_with_chain():
    one = DurableArchiveManifest.derive_archive_id(
        "one",
        fp("checkpoint"),
    )
    two = DurableArchiveManifest.derive_archive_id(
        "two",
        fp("checkpoint"),
    )
    assert one != two


def test_manifest_to_dict_can_omit_entries():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    compact = archive.manifest.to_dict(
        include_entries=False
    )
    assert "entries" not in compact
    assert compact["node_count"] == 2
    assert compact["entries_digest"] == (
        archive.manifest.entries_digest
    )


def test_archive_serialization_has_no_deletion_authority():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    data = archive.to_dict()
    serialized = str(data).lower()
    assert "delete" not in serialized
    assert "prune" not in serialized
    assert "deletion_safe" not in serialized


def test_archive_verification_to_dict():
    report = DurableArchiveVerification(
        True,
        "archive",
        "chain",
        fp("checkpoint"),
        2,
        fp("root"),
        2,
        3,
        fp("current"),
        True,
        True,
        True,
        (),
    )
    data = report.to_dict()
    assert data["valid"] is True
    assert data["checkpoint_valid"] is True
    assert data["prefix_valid"] is True
    assert data["committed_ancestor"] is True


def test_archive_verification_validation():
    with pytest.raises(ValueError):
        DurableArchiveVerification(
            True,
            "",
            "chain",
            fp("checkpoint"),
            0,
            "0" * 64,
            0,
            0,
            "0" * 64,
            True,
            True,
            True,
            (),
        )
    with pytest.raises(ValueError):
        DurableArchiveVerification(
            True,
            "archive",
            "chain",
            "bad",
            0,
            "0" * 64,
            0,
            0,
            "0" * 64,
            True,
            True,
            True,
            (),
        )


class UnsupportedNode:
    sequence = 1
    previous_hash = "0" * 64


def test_builder_rejects_unsupported_node_shape():
    _, _, _, builder = journal_fixture()
    with pytest.raises(
        DurableArchiveError,
        match="unsupported",
    ):
        builder._entry(
            UnsupportedNode()
        )


def test_entries_digest_changes_with_entry_kind():
    first = DurableArchiveEntry(
        1,
        "0" * 64,
        fp("node"),
        "kind.one",
        fp("object"),
    )
    second = replace(
        first,
        kind="kind.two",
    )
    assert (
        DurableArchiveManifest.compute_entries_digest(
            (first,)
        )
        != DurableArchiveManifest.compute_entries_digest(
            (second,)
        )
    )


def test_signed_archive_to_dict_contains_manifest_digest():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    data = archive.to_dict()
    assert data["manifest_digest"] == archive.manifest.digest
    assert data["signature"]["artifact_type"] == (
        "durable-archive-manifest"
    )


def test_checkpoint_registry_tamper_invalidates_archive():
    backend, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    node = checkpoints._chain.snapshot()[0]
    record = backend.get(
        checkpoints._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    signature = dict(payload["signature"])
    signature["signature"] = fp("tampered")
    payload["signature"] = signature
    backend.compare_and_swap(
        checkpoints._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(
            node,
            payload=payload,
        ),
    )
    report = builder.inspect(
        archive,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert not report.checkpoint_valid


def test_historical_chain_corruption_invalidates_archive():
    backend, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    root = checkpoint.checkpoint.root_hash
    record = backend.get(
        journal.namespace,
        journal._event_key(root),
    )
    backend.compare_and_swap(
        journal.namespace,
        journal._event_key(root),
        expected_revision=record.revision,
        value=replace(
            record.value,
            summary="tampered",
        ),
    )
    report = builder.inspect(
        archive,
        checkpoint,
        journal,
    )
    assert not report.valid
    assert not report.prefix_valid
    assert not report.committed_ancestor


def test_archive_manifest_contains_only_checkpoint_prefix_not_current_head():
    _, journal, checkpoints, builder = journal_fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    append_events(journal, 5)
    assert archive.manifest.node_count == 2
    assert archive.manifest.checkpoint_sequence == 2
    assert journal.length() == 7


def test_archive_manifest_object_digest_for_journal_is_node_hash():
    _, journal, checkpoints, builder = journal_fixture()
    events = append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    entry = archive.manifest.entries[0]
    assert entry.object_digest == events[0].event_hash
    assert entry.node_hash == events[0].event_hash
