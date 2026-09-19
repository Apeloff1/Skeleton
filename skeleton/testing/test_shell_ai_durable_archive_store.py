"""Portable durable archive repository and historical read-through tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import (
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_archive import (
    DurableArchiveManifestBuilder,
)
from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchivedNode,
    DurableArchivedNodeType,
    DurableArchiveHead,
    DurableArchiveRepository,
    DurableArchiveRootIndex,
    DurableArchiveStoreError,
    DurableArchiveStoreReport,
    StoredDurableArchive,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
)
from skeleton.shells.receipts import (
    ExecutionReceipt,
)


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(
        value.encode()
    ).hexdigest()


def checkpoint_signer():
    return ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )


def archive_signer():
    return ArtifactSigner(
        "archive",
        b"a" * 32,
        clock=lambda: 200.0,
    )


def journal_fixture(
    *,
    archive_clock=lambda: 300.0,
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=100,
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
    repository = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archive-store",
        clock=archive_clock,
    )
    return (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    )


def append_events(
    journal,
    count,
    *,
    start=0,
):
    result = []
    for index in range(
        start,
        start + count,
    ):
        result.append(
            journal.append(
                "archive.event",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
                data={"index": index},
            )
        )
    return tuple(result)


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(
            f"receipt:{index}"
        ),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=index + 1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
        metadata={"index": index},
    )


def archive_current(
    chain_id,
    chain,
    checkpoints,
    builder,
    repository,
):
    checkpoint = checkpoints.publish(
        chain_id,
        chain,
    )
    archive = builder.build(
        checkpoint,
        chain,
    )
    report = repository.put(
        archive,
        checkpoint,
        chain,
    )
    return checkpoint, archive, report


def test_store_nonempty_journal_archive():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        3,
    )
    checkpoint, archive, report = (
        archive_current(
            "journal",
            journal,
            checkpoints,
            builder,
            repository,
        )
    )
    assert report.fresh_write
    assert report.sequence == 3
    assert report.node_count == 3
    assert report.root_hash == events[-1].event_hash
    assert report.archive_id == archive.manifest.archive_id
    assert (
        report.checkpoint_digest
        == checkpoint.checkpoint.digest
    )
    assert report.repaired_indexes == 4
    assert repository.verify_root(
        "journal",
        report.root_hash,
    )


def test_store_empty_archive():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    _, archive, report = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    assert report.sequence == 0
    assert report.node_count == 0
    assert report.root_hash == "0" * 64
    assert report.repaired_indexes == 1
    stored = repository.require(
        archive.manifest.archive_id
    )
    assert stored.node_hashes == ()
    assert repository.latest(
        "journal"
    ).sequence == 0


def test_snapshot_each_archived_journal_prefix():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        4,
    )
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    for index, event in enumerate(
        events,
        start=1,
    ):
        prefix = repository.snapshot_at(
            "journal",
            event.event_hash,
        )
        assert prefix == events[:index]
        assert repository.verify_root(
            "journal",
            event.event_hash,
        )


def test_fresh_repository_reconstructs_journal_archive():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        3,
    )
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )

    fresh = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archive-store",
        clock=lambda: 999.0,
    )
    stored = fresh.require(
        archive.manifest.archive_id
    )
    assert stored.manifest == archive
    assert fresh.snapshot_at(
        "journal",
        events[1].event_hash,
    ) == events[:2]
    assert fresh.verify_root(
        "journal",
        events[-1].event_hash,
    )


def test_same_archive_put_is_idempotent_across_store_clock():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture(
        archive_clock=lambda: 300.0
    )
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    first = repository.put(
        archive,
        checkpoint,
        journal,
    )

    fresh = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archive-store",
        clock=lambda: 999.0,
    )
    second = fresh.put(
        archive,
        checkpoint,
        journal,
    )
    assert first.fresh_write
    assert not second.fresh_write
    assert second.archive_id == first.archive_id
    assert second.root_hash == first.root_hash
    stored = fresh.require(
        archive.manifest.archive_id
    )
    assert stored.stored_at == 300.0


def test_larger_archive_reuses_earlier_root_indexes():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    first_events = append_events(
        journal,
        2,
    )
    _, first_archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    first_index = repository.root_index(
        "journal",
        first_events[0].event_hash,
    )
    assert first_index.archive_id == (
        first_archive.manifest.archive_id
    )

    later_events = append_events(
        journal,
        3,
        start=2,
    )
    _, later_archive, later_report = (
        archive_current(
            "journal",
            journal,
            checkpoints,
            builder,
            repository,
        )
    )
    assert later_report.sequence == 5
    assert (
        repository.latest("journal")
        .archive_id
        == later_archive.manifest.archive_id
    )
    retained_index = repository.root_index(
        "journal",
        first_events[0].event_hash,
    )
    assert retained_index.archive_id == first_index.archive_id
    assert retained_index.sequence == first_index.sequence
    assert retained_index.root_hash == first_index.root_hash
    assert len(retained_index.replicas) == 2
    assert tuple(
        replica.archive_id
        for replica in retained_index.replicas
    ) == (
        first_archive.manifest.archive_id,
        later_archive.manifest.archive_id,
    )
    assert repository.snapshot_at(
        "journal",
        first_events[0].event_hash,
    ) == first_events[:1]
    assert repository.snapshot_at(
        "journal",
        later_events[-1].event_hash,
    ) == first_events + later_events


def test_archive_head_never_rolls_back():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 2)
    first_checkpoint, first_archive, _ = (
        archive_current(
            "journal",
            journal,
            checkpoints,
            builder,
            repository,
        )
    )
    append_events(
        journal,
        2,
        start=2,
    )
    _, later_archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    assert (
        repository.latest("journal")
        .archive_id
        == later_archive.manifest.archive_id
    )
    repository.put(
        first_archive,
        first_checkpoint,
        journal,
    )
    assert (
        repository.latest("journal")
        .archive_id
        == later_archive.manifest.archive_id
    )


def test_deleted_root_index_is_repaired_on_retry():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        3,
    )
    checkpoint, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    root_key = repository._root_key(
        "journal",
        events[1].event_hash,
    )
    record = backend.get(
        repository.namespace,
        root_key,
    )
    backend.delete(
        repository.namespace,
        root_key,
        expected_revision=record.revision,
    )
    assert repository.root_index(
        "journal",
        events[1].event_hash,
    ) is None

    report = repository.put(
        archive,
        checkpoint,
        journal,
    )
    assert not report.fresh_write
    assert report.repaired_indexes >= 1
    assert repository.root_index(
        "journal",
        events[1].event_hash,
    ) is not None
    assert repository.snapshot_at(
        "journal",
        events[1].event_hash,
    ) == events[:2]


def test_deleted_archive_head_is_repaired_on_retry():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 2)
    checkpoint, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    key = repository._head_key(
        "journal"
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    backend.delete(
        repository.namespace,
        key,
        expected_revision=record.revision,
    )
    assert repository.latest(
        "journal"
    ) is None
    repository.put(
        archive,
        checkpoint,
        journal,
    )
    assert repository.latest(
        "journal"
    ).sequence == 2


def test_deleted_archived_node_breaks_archive_verification():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        2,
    )
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    stored = repository.get(
        archive.manifest.archive_id
    )
    key = repository._node_key(
        "journal",
        events[0].event_hash,
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    backend.delete(
        repository.namespace,
        key,
        expected_revision=record.revision,
    )
    assert not repository.verify_archive(
        stored
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="missing",
    ):
        repository.snapshot_at(
            "journal",
            events[-1].event_hash,
        )


def test_tampered_archived_journal_payload_is_rejected():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        1,
    )
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    key = repository._node_key(
        "journal",
        events[0].event_hash,
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    payload["summary"] = "tampered"
    raw["payload"] = payload
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    stored = repository.get(
        archive.manifest.archive_id
    )
    assert not repository.verify_archive(
        stored
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="native digest",
    ):
        repository.get_node(
            "journal",
            events[0].event_hash,
        )


def test_tampered_archive_manifest_signature_is_rejected():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    key = repository._archive_key(
        archive.manifest.archive_id
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    signed = dict(raw["manifest"])
    signature = dict(
        signed["signature"]
    )
    signature["signature"] = "f" * 64
    signed["signature"] = signature
    raw["manifest"] = signed
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="signature verification",
    ):
        repository.get(
            archive.manifest.archive_id
        )


def test_root_index_tamper_is_rejected():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        2,
    )
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    key = repository._root_key(
        "journal",
        events[0].event_hash,
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    raw["sequence"] = 99
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
    ):
        repository.snapshot_at(
            "journal",
            events[0].event_hash,
        )


def test_archive_record_identity_tamper_is_rejected():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    key = repository._archive_key(
        archive.manifest.archive_id
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    signed = dict(raw["manifest"])
    manifest = dict(
        signed["manifest"]
    )
    manifest["archive_id"] = (
        "x" * 64
    )
    signed["manifest"] = manifest
    raw["manifest"] = signed
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        (
            DurableArchiveStoreError,
            ValueError,
        )
    ):
        repository.get(
            archive.manifest.archive_id
        )


def test_store_receipt_archive_and_reconstruct_payloads():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    values = tuple(
        receipt(index)
        for index in range(3)
    )
    nodes = tuple(
        receipts.append(value)
        for value in values
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
    repository = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archive-store",
        clock=lambda: 300.0,
    )
    _, archive, report = archive_current(
        "receipts",
        receipts,
        checkpoints,
        builder,
        repository,
    )
    assert report.node_count == 3
    restored = repository.snapshot_at(
        "receipts",
        nodes[-1].receipt_hash,
    )
    assert restored == nodes
    assert tuple(
        item.receipt
        for item in restored
    ) == values
    assert repository.require(
        archive.manifest.archive_id
    ).manifest == archive


def test_tampered_archived_receipt_payload_is_rejected():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    node = receipts.append(
        receipt(0)
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
    repository = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archive-store",
    )
    archive_current(
        "receipts",
        receipts,
        checkpoints,
        builder,
        repository,
    )
    key = repository._node_key(
        "receipts",
        node.receipt_hash,
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    receipt_raw = dict(
        payload["receipt"]
    )
    receipt_raw["stdout_bytes"] = 999
    payload["receipt"] = receipt_raw
    raw["payload"] = payload
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="native digest",
    ):
        repository.get_node(
            "receipts",
            node.receipt_hash,
        )


def test_store_generic_evidence_nodes():
    backend = InMemoryFencedStore()
    chain = ContentAddressedEvidenceChain(
        backend,
        namespace="generic",
    )
    nodes = (
        chain.append(
            "generic.one",
            {"value": 1},
        ),
        chain.append(
            "generic.two",
            {"value": 2},
        ),
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
        namespace="checkpoints",
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer(),
    )
    repository = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archive-store",
    )
    archive_current(
        "generic",
        chain,
        checkpoints,
        builder,
        repository,
    )
    restored = repository.snapshot_at(
        "generic",
        nodes[-1].node_hash,
    )
    assert restored == nodes
    assert repository.verify_root(
        "generic",
        nodes[0].node_hash,
    )


def test_unsupported_archive_node_type_is_rejected():
    with pytest.raises(
        DurableArchiveStoreError,
        match="unsupported",
    ):
        DurableArchiveRepository._encode_node(
            "chain",
            object(),
        )


def test_archive_backed_resolver_uses_live_chain_when_available():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        2,
    )
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    resolver = ArchiveBackedHistoricalChain(
        "journal",
        journal,
        repository,
    )
    assert resolver.snapshot_at(
        events[-1].event_hash
    ) == events
    assert resolver.verify_root(
        events[0].event_hash
    )
    assert resolver.root_is_ancestor(
        events[0].event_hash
    )
    assert resolver.head() == journal.head()
    assert resolver.root_hash() == journal.root_hash()
    assert resolver.length() == journal.length()


class ForgetfulHistoricalView:
    """Live head remains readable while old roots are deliberately unavailable."""

    def __init__(
        self,
        delegate,
        forgotten_roots,
    ):
        self.delegate = delegate
        self.forgotten_roots = set(
            forgotten_roots
        )

    def head(self):
        return self.delegate.head()

    def verify(self):
        return self.delegate.verify()

    def snapshot(self):
        return self.delegate.snapshot()

    def root_hash(self):
        return self.delegate.root_hash()

    def length(self):
        return self.delegate.length()

    def snapshot_at(self, root_hash):
        if root_hash in self.forgotten_roots:
            raise KeyError(root_hash)
        return self.delegate.snapshot_at(
            root_hash
        )

    def verify_root(self, root_hash):
        if root_hash in self.forgotten_roots:
            return False
        return self.delegate.verify_root(
            root_hash
        )

    def root_is_ancestor(self, root_hash):
        if root_hash in self.forgotten_roots:
            return False
        return self.delegate.root_is_ancestor(
            root_hash
        )


def test_archive_backed_resolver_falls_back_for_forgotten_root():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        3,
    )
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    forgotten = events[0].event_hash
    live = ForgetfulHistoricalView(
        journal,
        {forgotten},
    )
    resolver = ArchiveBackedHistoricalChain(
        "journal",
        live,
        repository,
    )
    assert resolver.snapshot_at(
        forgotten
    ) == events[:1]
    assert resolver.verify_root(
        forgotten
    )
    assert resolver.root_is_ancestor(
        forgotten
    )


def test_archive_backed_resolver_fails_if_root_absent_everywhere():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    missing = fp("missing-root")
    resolver = ArchiveBackedHistoricalChain(
        "journal",
        ForgetfulHistoricalView(
            journal,
            {missing},
        ),
        repository,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="unavailable",
    ):
        resolver.snapshot_at(
            missing
        )
    assert not resolver.verify_root(
        missing
    )
    assert not resolver.root_is_ancestor(
        missing
    )


def test_archive_backed_resolver_fresh_process():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        2,
    )
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    fresh_repository = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archive-store",
    )
    forgotten = events[0].event_hash
    resolver = ArchiveBackedHistoricalChain(
        "journal",
        ForgetfulHistoricalView(
            journal,
            {forgotten},
        ),
        fresh_repository,
    )
    assert resolver.snapshot_at(
        forgotten
    ) == events[:1]


def test_wrong_archive_signer_cannot_read_archive():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    wrong = DurableArchiveRepository(
        backend,
        checkpoints,
        ArtifactSigner(
            "wrong",
            b"w" * 32,
        ),
        namespace="archive-store",
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="signature",
    ):
        wrong.get(
            archive.manifest.archive_id
        )


def test_noncanonical_checkpoint_is_rejected_on_put():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    foreign = replace(
        checkpoint,
        chain_node_hash=fp(
            "foreign-node"
        ),
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="canonical",
    ):
        repository.put(
            archive,
            foreign,
            journal,
        )


def test_manifest_checkpoint_mismatch_is_rejected():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    first = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        first,
        journal,
    )
    append_events(
        journal,
        1,
        start=1,
    )
    second = checkpoints.publish(
        "journal",
        journal,
    )
    with pytest.raises(
        Exception,
    ):
        repository.put(
            archive,
            second,
            journal,
        )


def test_root_index_first_archive_is_stable_across_later_archive():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        1,
    )
    _, first, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    append_events(
        journal,
        2,
        start=1,
    )
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    index = repository.root_index(
        "journal",
        events[0].event_hash,
    )
    assert index.archive_id == (
        first.manifest.archive_id
    )


def test_repair_indexes_is_idempotent():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 3)
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    assert repository.repair_indexes(
        archive.manifest.archive_id
    ) == 0
    assert repository.repair_indexes(
        archive.manifest.archive_id
    ) == 0


def test_repair_missing_archive_fails():
    (
        _,
        _,
        _,
        _,
        repository,
    ) = journal_fixture()
    with pytest.raises(
        DurableArchiveStoreError,
        match="missing",
    ):
        repository.repair_indexes(
            "missing"
        )


def test_require_missing_archive_fails():
    (
        _,
        _,
        _,
        _,
        repository,
    ) = journal_fixture()
    with pytest.raises(
        DurableArchiveStoreError,
        match="missing",
    ):
        repository.require(
            "missing"
        )


def test_snapshot_unarchived_root_fails():
    (
        _,
        _,
        _,
        _,
        repository,
    ) = journal_fixture()
    with pytest.raises(
        DurableArchiveStoreError,
        match="not archived",
    ):
        repository.snapshot_at(
            "journal",
            fp("missing"),
        )


def test_verify_unarchived_root_is_false():
    (
        _,
        _,
        _,
        _,
        repository,
    ) = journal_fixture()
    assert not repository.verify_root(
        "journal",
        fp("missing"),
    )


def test_genesis_snapshot_is_empty():
    (
        _,
        _,
        _,
        _,
        repository,
    ) = journal_fixture()
    assert repository.snapshot_at(
        "journal",
        "0" * 64,
    ) == ()


@pytest.mark.parametrize(
    "namespace",
    ["", "x" * 129],
)
def test_repository_namespace_validation(namespace):
    backend = InMemoryFencedStore()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
    )
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableArchiveRepository(
            backend,
            checkpoints,
            archive_signer(),
            namespace=namespace,
        )


@pytest.mark.parametrize(
    "maximum",
    [0, -1, True, 1.2],
)
def test_repository_node_bound_validation(maximum):
    backend = InMemoryFencedStore()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
    )
    with pytest.raises(
        ValueError,
        match="max_nodes_per_archive",
    ):
        DurableArchiveRepository(
            backend,
            checkpoints,
            archive_signer(),
            max_nodes_per_archive=maximum,
        )


@pytest.mark.parametrize(
    "retries",
    [0, 129, True, 1.2],
)
def test_repository_retry_bound_validation(retries):
    backend = InMemoryFencedStore()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
    )
    with pytest.raises(
        ValueError,
        match="max_cas_retries",
    ):
        DurableArchiveRepository(
            backend,
            checkpoints,
            archive_signer(),
            max_cas_retries=retries,
        )


def test_repository_constructor_type_validation():
    backend = InMemoryFencedStore()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
    )
    with pytest.raises(TypeError):
        DurableArchiveRepository(
            object(),
            checkpoints,
            archive_signer(),
        )
    with pytest.raises(TypeError):
        DurableArchiveRepository(
            backend,
            object(),
            archive_signer(),
        )
    with pytest.raises(TypeError):
        DurableArchiveRepository(
            backend,
            checkpoints,
            object(),
        )
    with pytest.raises(TypeError):
        DurableArchiveRepository(
            backend,
            checkpoints,
            archive_signer(),
            clock=object(),
        )


def test_put_type_validation():
    (
        _,
        journal,
        checkpoints,
        _,
        repository,
    ) = journal_fixture()
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    with pytest.raises(TypeError):
        repository.put(
            object(),
            checkpoint,
            journal,
        )
    with pytest.raises(TypeError):
        repository.put(
            object(),
            object(),
            journal,
        )


def test_archive_node_validation():
    with pytest.raises(ValueError):
        DurableArchivedNode(
            "",
            DurableArchivedNodeType.AI_DECISION_EVENT,
            1,
            fp("prev"),
            fp("node"),
            fp("obj"),
            {},
        )
    with pytest.raises(ValueError):
        DurableArchivedNode(
            "chain",
            DurableArchivedNodeType.AI_DECISION_EVENT,
            0,
            fp("prev"),
            fp("node"),
            fp("obj"),
            {},
        )
    with pytest.raises(ValueError):
        DurableArchivedNode(
            "chain",
            DurableArchivedNodeType.AI_DECISION_EVENT,
            1,
            "bad",
            fp("node"),
            fp("obj"),
            {},
        )


def test_root_index_validation():
    with pytest.raises(ValueError):
        DurableArchiveRootIndex(
            "chain",
            fp("root"),
            -1,
            "archive",
            fp("manifest"),
        )
    with pytest.raises(ValueError):
        DurableArchiveRootIndex(
            "chain",
            fp("root"),
            0,
            "archive",
            fp("manifest"),
        )


def test_archive_head_validation():
    with pytest.raises(ValueError):
        DurableArchiveHead(
            "chain",
            -1,
            fp("root"),
            "archive",
            fp("manifest"),
        )


def test_store_report_to_dict():
    report = DurableArchiveStoreReport(
        "archive",
        "chain",
        1,
        fp("root"),
        1,
        fp("manifest"),
        fp("checkpoint"),
        True,
        2,
    )
    data = report.to_dict()
    assert data["archive_id"] == "archive"
    assert data["fresh_write"] is True
    assert data["repaired_indexes"] == 2


def test_stored_archive_validation_count():
    (
        _,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    _, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    stored = repository.require(
        archive.manifest.archive_id
    )
    with pytest.raises(ValueError):
        StoredDurableArchive(
            stored.revision,
            stored.manifest,
            stored.checkpoint,
            (),
            stored.stored_at,
        )


def test_archive_node_payload_is_immutable():
    archived = DurableArchivedNode(
        "chain",
        DurableArchivedNodeType.EVIDENCE_NODE,
        1,
        "0" * 64,
        fp("node"),
        fp("node"),
        {"value": 1},
    )
    with pytest.raises(TypeError):
        archived.payload["value"] = 2


def test_archive_record_rejects_different_payload_same_archive_id():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    append_events(journal, 1)
    checkpoint, archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    key = repository._archive_key(
        archive.manifest.archive_id
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    raw["stored_at"] = 999.0
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
    ):
        repository.put(
            archive,
            checkpoint,
            journal,
        )


def test_archive_backed_resolver_type_validation():
    (
        _,
        journal,
        _,
        _,
        repository,
    ) = journal_fixture()
    with pytest.raises(ValueError):
        ArchiveBackedHistoricalChain(
            "",
            journal,
            repository,
        )
    with pytest.raises(TypeError):
        ArchiveBackedHistoricalChain(
            "journal",
            object(),
            repository,
        )
    with pytest.raises(TypeError):
        ArchiveBackedHistoricalChain(
            "journal",
            journal,
            object(),
        )


def test_archive_repository_does_not_delete_live_nodes():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    events = append_events(
        journal,
        3,
    )
    archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    for event in events:
        assert backend.get(
            journal.namespace,
            journal._event_key(
                event.event_hash
            ),
        ) is not None
    assert journal.snapshot() == events

def two_replica_journal_fixture():
    (
        backend,
        journal,
        checkpoints,
        builder,
        repository,
    ) = journal_fixture()
    first_events = append_events(
        journal,
        2,
    )
    _, first_archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    append_events(
        journal,
        3,
        start=2,
    )
    _, second_archive, _ = archive_current(
        "journal",
        journal,
        checkpoints,
        builder,
        repository,
    )
    root = first_events[0].event_hash
    index = repository.root_index(
        "journal",
        root,
    )
    assert index is not None
    assert len(index.replicas) == 2
    return (
        backend,
        journal,
        repository,
        first_events,
        first_archive,
        second_archive,
        root,
    )


def delete_archive_record(
    backend,
    repository,
    archive_id,
):
    key = repository._archive_key(
        archive_id
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    assert record is not None
    backend.delete(
        repository.namespace,
        key,
        expected_revision=record.revision,
    )


def test_historical_root_falls_back_when_primary_archive_is_missing():
    (
        backend,
        _,
        repository,
        first_events,
        first_archive,
        second_archive,
        root,
    ) = two_replica_journal_fixture()
    delete_archive_record(
        backend,
        repository,
        first_archive.manifest.archive_id,
    )
    resolution = repository.resolve_root(
        "journal",
        root,
    )
    assert (
        resolution.archive_id
        == second_archive.manifest.archive_id
    )
    assert resolution.replica_index == 1
    assert repository.snapshot_at(
        "journal",
        root,
    ) == first_events[:1]
    assert repository.verify_root(
        "journal",
        root,
    )


def test_historical_root_falls_back_when_primary_archive_record_is_tampered():
    (
        backend,
        _,
        repository,
        first_events,
        first_archive,
        second_archive,
        root,
    ) = two_replica_journal_fixture()
    key = repository._archive_key(
        first_archive.manifest.archive_id
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    raw["stored_at"] = (
        float(raw["stored_at"])
        + 1.0
    )
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    resolution = repository.resolve_root(
        "journal",
        root,
    )
    assert (
        resolution.archive_id
        == second_archive.manifest.archive_id
    )
    assert repository.snapshot_at(
        "journal",
        root,
    ) == first_events[:1]


def test_historical_root_falls_back_when_primary_archive_node_is_tampered():
    (
        backend,
        _,
        repository,
        first_events,
        first_archive,
        second_archive,
        root,
    ) = two_replica_journal_fixture()
    node_key = repository._node_key(
        "journal",
        root,
    )
    # Nodes are content-addressed and shared by replicas, so corrupting the
    # shared node correctly invalidates every replica. This test instead
    # corrupts a primary-only later node so primary archive verification fails
    # while the one-node historical prefix remains reconstructable from replica
    # metadata in the second archive.
    primary = repository.require(
        first_archive.manifest.archive_id
    )
    primary_only_hash = (
        primary.node_hashes[-1]
    )
    if primary_only_hash == root:
        pytest.skip(
            "fixture has no primary-only node"
        )
    key = repository._node_key(
        "journal",
        primary_only_hash,
    )
    record = backend.get(
        repository.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    payload["summary"] = "tampered-primary-only"
    raw["payload"] = payload
    backend.compare_and_swap(
        repository.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    resolution = repository.resolve_root(
        "journal",
        root,
    )
    assert (
        resolution.archive_id
        == second_archive.manifest.archive_id
    )
    assert repository.snapshot_at(
        "journal",
        root,
    ) == first_events[:1]


def test_historical_root_fails_closed_when_all_archive_records_are_missing():
    (
        backend,
        _,
        repository,
        _,
        first_archive,
        second_archive,
        root,
    ) = two_replica_journal_fixture()
    delete_archive_record(
        backend,
        repository,
        first_archive.manifest.archive_id,
    )
    delete_archive_record(
        backend,
        repository,
        second_archive.manifest.archive_id,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="all archive replicas",
    ):
        repository.snapshot_at(
            "journal",
            root,
        )
    assert not repository.verify_root(
        "journal",
        root,
    )


def test_root_replica_list_is_stable_across_fresh_reader():
    (
        backend,
        _,
        repository,
        _,
        _,
        _,
        root,
    ) = two_replica_journal_fixture()
    fresh = DurableArchiveRepository(
        backend,
        repository.checkpoints,
        archive_signer(),
        namespace=repository.namespace,
    )
    index = fresh.root_index(
        "journal",
        root,
    )
    assert len(index.replicas) == 2
    assert index.replicas[0].archive_id == index.archive_id


def test_resolve_root_reports_primary_replica_when_healthy():
    (
        _,
        _,
        repository,
        _,
        first_archive,
        _,
        root,
    ) = two_replica_journal_fixture()
    resolution = repository.resolve_root(
        "journal",
        root,
    )
    assert resolution.replica_index == 0
    assert (
        resolution.archive_id
        == first_archive.manifest.archive_id
    )
    assert resolution.sequence == 1


def test_root_replica_manifest_conflict_is_rejected():
    (
        _,
        _,
        repository,
        _,
        first_archive,
        _,
        root,
    ) = two_replica_journal_fixture()
    index = repository.root_index(
        "journal",
        root,
    )
    conflicting = DurableArchiveRootIndex(
        index.chain_id,
        index.root_hash,
        index.sequence,
        first_archive.manifest.archive_id,
        fp("different-manifest"),
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="different manifest",
    ):
        repository._put_root_index(
            conflicting
        )

