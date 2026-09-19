"""Signed hot-floor and destructive durable pruning integration tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalConflict,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import DurableArchiveManifestBuilder
from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchiveRepository,
    DurableArchiveStoreError,
)
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionPolicy,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificateStore,
)
from skeleton.shells.ai.durable_destruction import DurableDestructionLedger
from skeleton.shells.ai.durable_hot_floor import (
    DurableHotFloorError,
    DurableHotFloorStore,
    HotFloorPosition,
)
from skeleton.shells.ai.durable_pruning import (
    DurablePruningError,
    DurablePruningExecutor,
    DurablePruningManualReview,
    DurablePruningPhase,
)
from skeleton.shells.ai.durable_pruning_authorization import (
    DurablePruningAuthorizationError,
    DurablePruningAuthorizationStore,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def signer(name: str, char: bytes, clock=lambda: 100.0):
    return ArtifactSigner(
        name,
        char * 32,
        clock=clock,
    )


def append_events(journal, count, *, start=0):
    result = []
    for index in range(start, start + count):
        result.append(
            journal.append(
                "pruning.event",
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
        fingerprint=fp(f"receipt:{index}"),
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


class Fixture:
    def __init__(
        self,
        *,
        kind="journal",
        backend=None,
        now=400.0,
        max_items=100,
    ):
        self.kind = kind
        self.now = [float(now)]
        self.backend = backend or InMemoryFencedStore()
        self.floor_signer = signer(
            "hot-floor",
            b"f",
            clock=lambda: self.now[0],
        )
        self.floor_store = DurableHotFloorStore(
            self.backend,
            self.floor_signer,
            namespace="hot-floors",
            clock=lambda: self.now[0],
        )
        if kind == "journal":
            self.chain = DistributedAIDecisionJournal(
                self.backend,
                namespace="journal",
                max_events=20,
                clock=lambda: 10.0,
                hot_floor_store=self.floor_store,
                hot_floor_chain_id="journal",
            )
            self.chain_id = "journal"
            self.first = append_events(
                self.chain,
                6,
            )
        elif kind == "receipts":
            self.chain = DistributedReceiptChain(
                self.backend,
                namespace="receipts",
                max_receipts=20,
                hot_floor_store=self.floor_store,
                hot_floor_chain_id="receipts",
            )
            self.chain_id = "receipts"
            self.first = tuple(
                self.chain.append(
                    receipt(index)
                )
                for index in range(6)
            )
        else:
            raise ValueError("unknown fixture kind")

        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            signer("checkpoint", b"c"),
            namespace=f"{kind}-checkpoints",
            clock=lambda: 100.0,
        )
        self.archive_signer = signer(
            "archive",
            b"a",
            clock=lambda: 200.0,
        )
        self.archive_builder = DurableArchiveManifestBuilder(
            self.checkpoints,
            self.archive_signer,
            clock=lambda: 200.0,
        )
        self.archives = DurableArchiveRepository(
            self.backend,
            self.checkpoints,
            self.archive_signer,
            namespace=f"{kind}-archives",
            clock=lambda: 300.0,
        )
        checkpoint = self.checkpoints.publish(
            self.chain_id,
            self.chain,
        )
        archive = self.archive_builder.build(
            checkpoint,
            self.chain,
        )
        self.archives.put(
            archive,
            checkpoint,
            self.chain,
        )
        self.archive = archive
        if kind == "journal":
            self.later = append_events(
                self.chain,
                2,
                start=6,
            )
        else:
            self.later = tuple(
                self.chain.append(
                    receipt(index)
                )
                for index in range(6, 8)
            )

        self.retention_planner = DurableRetentionPlanner(
            self.checkpoints,
            DurableRetentionPolicy(
                minimum_live_tail=2,
                minimum_archive_batch=2,
                target_utilization=0.25,
                warning_utilization=0.75,
                critical_utilization=0.95,
                max_protected_roots=32,
            ),
        )
        self.retention = self.retention_planner.plan(
            self.chain_id,
            self.chain,
        )
        self.compaction = DurableCompactionPlanner(
            self.archives,
            DurableCompactionPolicy(
                minimum_live_tail=2,
                maximum_candidate_nodes=20,
                max_protected_roots=32,
            ),
        )
        assert self.compaction.require_ready(
            self.retention,
            self.chain,
        ).ready

        self.certificate_store = DurableCompactionCertificateStore(
            self.backend,
            signer(
                "certificate",
                b"s",
                clock=lambda: self.now[0],
            ),
            self.compaction,
            namespace=f"{kind}-certificates",
            ttl_seconds=60.0,
            max_ttl_seconds=3600.0,
            clock=lambda: self.now[0],
        )
        self.certificate = self.certificate_store.issue(
            self.retention,
            self.chain,
        )
        self.authorization_store = DurablePruningAuthorizationStore(
            self.backend,
            signer(
                "pruning",
                b"p",
                clock=lambda: self.now[0],
            ),
            self.certificate_store,
            namespace=f"{kind}-authorizations",
            ttl_seconds=30.0,
            max_ttl_seconds=600.0,
            max_delete_items=max_items,
            clock=lambda: self.now[0],
            nonce_factory=lambda: f"nonce-{kind}",
        )
        self.authorization = self.authorization_store.issue(
            self.certificate,
            self.retention,
            self.chain,
            operator_id="operator",
            max_delete_items=max_items,
        )
        self.destruction_ledger = DurableDestructionLedger(
            self.backend,
            signer(
                "destruction",
                b"d",
                clock=lambda: self.now[0],
            ),
            namespace=f"{kind}-destruction",
            clock=lambda: self.now[0],
        )
        self.executor = DurablePruningExecutor(
            self.backend,
            self.authorization_store,
            self.floor_store,
            destruction_ledger=self.destruction_ledger,
            namespace=f"{kind}-pruning",
            max_items=max_items,
            clock=lambda: self.now[0],
        )

    @property
    def cutoff_sequence(self):
        return self.authorization.authorization.cutoff_sequence

    @property
    def cutoff_root(self):
        return self.authorization.authorization.cutoff_root


def test_floor_store_starts_at_genesis():
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
    )
    assert store.current("journal") is None
    assert store.position("journal") == HotFloorPosition.genesis()


def test_floor_advance_is_signed_and_monotonic():
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
        clock=lambda: 10.0,
    )
    first = store.advance(
        chain_id="journal",
        sequence=3,
        root_hash=fp("root-3"),
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    assert first.floor.sequence == 3
    assert first.floor.previous_sequence == 0
    assert first.floor.previous_root_hash == "0" * 64
    assert store.position("journal").root_hash == fp("root-3")

    second = store.advance(
        chain_id="journal",
        sequence=5,
        root_hash=fp("root-5"),
        archive_id="archive-2",
        archive_manifest_digest=fp("archive-2"),
        compaction_certificate_id=fp("certificate-2"),
        pruning_authorization_id=fp("authorization-2"),
        operation_id=fp("operation-2"),
        fencing_token=2,
        expected_previous_sequence=3,
        expected_previous_root=fp("root-3"),
    )
    assert second.floor.previous_sequence == 3
    assert second.floor.sequence == 5


def test_floor_cannot_move_backwards():
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
    )
    store.advance(
        chain_id="journal",
        sequence=3,
        root_hash=fp("root-3"),
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="backwards",
    ):
        store.advance(
            chain_id="journal",
            sequence=2,
            root_hash=fp("root-2"),
            archive_id="archive",
            archive_manifest_digest=fp("archive"),
            compaction_certificate_id=fp("certificate"),
            pruning_authorization_id=fp("authorization"),
            operation_id=fp("operation-2"),
            fencing_token=2,
        )


def test_same_floor_retry_is_idempotent():
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
        clock=lambda: 10.0,
    )
    kwargs = dict(
        chain_id="journal",
        sequence=3,
        root_hash=fp("root-3"),
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    first = store.advance(**kwargs)
    second = store.advance(**kwargs)
    assert second == first


def test_same_floor_sequence_different_authority_is_rejected():
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
    )
    store.advance(
        chain_id="journal",
        sequence=3,
        root_hash=fp("root-3"),
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="different authority",
    ):
        store.advance(
            chain_id="journal",
            sequence=3,
            root_hash=fp("root-3"),
            archive_id="archive",
            archive_manifest_digest=fp("archive"),
            compaction_certificate_id=fp("certificate"),
            pruning_authorization_id=fp("different"),
            operation_id=fp("operation"),
            fencing_token=2,
        )


def test_floor_previous_position_is_fenced():
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
    )
    store.advance(
        chain_id="journal",
        sequence=3,
        root_hash=fp("root-3"),
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="previous sequence",
    ):
        store.advance(
            chain_id="journal",
            sequence=5,
            root_hash=fp("root-5"),
            archive_id="archive",
            archive_manifest_digest=fp("archive"),
            compaction_certificate_id=fp("certificate"),
            pruning_authorization_id=fp("authorization-2"),
            operation_id=fp("operation-2"),
            fencing_token=2,
            expected_previous_sequence=0,
            expected_previous_root="0" * 64,
        )


def test_floor_signature_tamper_is_detected():
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
    )
    item = store.advance(
        chain_id="journal",
        sequence=3,
        root_hash=fp("root-3"),
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    key = store._key("journal")
    record = backend.get(
        store.namespace,
        key,
    )
    payload = dict(record.value)
    payload["floor"] = dict(
        payload["floor"]
    )
    payload["floor"]["root_hash"] = fp(
        "tampered"
    )
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    with pytest.raises(DurableHotFloorError):
        store.current("journal")
    assert item.floor.root_hash == fp("root-3")


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_signed_floor_is_inert_before_cutoff_node_is_deleted(kind):
    fixture = Fixture(kind=kind)
    before = fixture.chain.snapshot()
    floor = fixture.floor_store.advance(
        chain_id=fixture.chain_id,
        sequence=fixture.cutoff_sequence,
        root_hash=fixture.cutoff_root,
        archive_id=fixture.authorization.authorization.archive_id,
        archive_manifest_digest=(
            fixture.authorization.authorization.archive_manifest_digest
        ),
        compaction_certificate_id=(
            fixture.certificate.certificate_id
        ),
        pruning_authorization_id=(
            fixture.authorization.authorization_id
        ),
        operation_id=fp(f"manual-floor-{kind}"),
        fencing_token=1,
    )
    assert floor.floor.sequence == 6
    assert not fixture.chain._hot_floor_active(
        fixture.chain.hot_floor()
    )
    assert fixture.chain.snapshot() == before
    assert fixture.chain.verify()
    assert fixture.chain.hot_length() == 8


def activate_manual_floor(fixture):
    floor = fixture.floor_store.advance(
        chain_id=fixture.chain_id,
        sequence=fixture.cutoff_sequence,
        root_hash=fixture.cutoff_root,
        archive_id=fixture.authorization.authorization.archive_id,
        archive_manifest_digest=(
            fixture.authorization.authorization.archive_manifest_digest
        ),
        compaction_certificate_id=(
            fixture.certificate.certificate_id
        ),
        pruning_authorization_id=(
            fixture.authorization.authorization_id
        ),
        operation_id=fp(f"manual-active-{fixture.kind}"),
        fencing_token=1,
    )
    for sequence in range(
        fixture.cutoff_sequence,
        0,
        -1,
    ):
        node = fixture.chain.get_by_sequence(
            sequence
        )
        node_hash = (
            node.event_hash
            if fixture.kind == "journal"
            else node.receipt_hash
        )
        node_key = (
            fixture.chain._event_key(node_hash)
            if fixture.kind == "journal"
            else fixture.chain._node_key(node_hash)
        )
        node_record = fixture.backend.get(
            fixture.chain.namespace,
            node_key,
        )
        fixture.backend.delete(
            fixture.chain.namespace,
            node_key,
            expected_revision=node_record.revision,
        )
        seq_key = fixture.chain._sequence_key(
            sequence
        )
        seq_record = fixture.backend.get(
            fixture.chain.namespace,
            seq_key,
        )
        if seq_record is not None:
            fixture.backend.delete(
                fixture.chain.namespace,
                seq_key,
                expected_revision=seq_record.revision,
            )
        if fixture.kind == "receipts":
            idx_key = fixture.chain._index_key(
                node.receipt.receipt_id
            )
            idx_record = fixture.backend.get(
                fixture.chain.namespace,
                idx_key,
            )
            if idx_record is not None:
                fixture.backend.delete(
                    fixture.chain.namespace,
                    idx_key,
                    expected_revision=idx_record.revision,
                )
    return floor


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_active_floor_verifies_only_live_suffix(kind):
    fixture = Fixture(kind=kind)
    activate_manual_floor(fixture)
    assert fixture.chain._hot_floor_active(
        fixture.chain.hot_floor()
    )
    assert fixture.chain.verify()
    assert fixture.chain.hot_length() == 2
    assert fixture.chain.snapshot() == fixture.later
    assert fixture.chain.length() == 8
    assert fixture.chain.root_hash() == (
        fixture.later[-1].event_hash
        if kind == "journal"
        else fixture.later[-1].receipt_hash
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_active_floor_root_is_trusted_ancestor(kind):
    fixture = Fixture(kind=kind)
    activate_manual_floor(fixture)
    assert fixture.chain.root_is_ancestor(
        fixture.cutoff_root
    )
    assert fixture.chain.verify_root(
        fixture.cutoff_root
    )
    assert fixture.chain.sequence_for_root(
        fixture.cutoff_root
    ) == fixture.cutoff_sequence


def test_pruned_journal_sequence_access_fails_closed():
    fixture = Fixture(kind="journal")
    activate_manual_floor(fixture)
    with pytest.raises(
        DistributedJournalConflict,
        match="compacted",
    ):
        fixture.chain.get_by_sequence(2)
    with pytest.raises(
        DistributedJournalConflict,
        match="compacted",
    ):
        fixture.chain.root_for_sequence(2)
    assert fixture.chain.root_for_sequence(6) == fixture.cutoff_root


def test_pruned_receipt_sequence_access_fails_closed():
    fixture = Fixture(kind="receipts")
    activate_manual_floor(fixture)
    with pytest.raises(
        DistributedReceiptConflict,
        match="compacted",
    ):
        fixture.chain.get_by_sequence(2)
    with pytest.raises(
        DistributedReceiptConflict,
        match="compacted",
    ):
        fixture.chain.root_for_sequence(2)
    assert fixture.chain.root_for_sequence(6) == fixture.cutoff_root


def test_pruned_receipt_id_is_absent_from_hot_index():
    fixture = Fixture(kind="receipts")
    old_receipt_id = fixture.first[0].receipt.receipt_id
    live_receipt_id = fixture.later[0].receipt.receipt_id
    activate_manual_floor(fixture)
    assert fixture.chain.find_by_receipt_id(
        old_receipt_id
    ) is None
    live = fixture.chain.require_receipt(
        live_receipt_id
    )
    assert live.committed
    assert live.node.sequence == 7


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_archive_backed_reader_restores_pruned_history(kind):
    fixture = Fixture(kind=kind)
    activate_manual_floor(fixture)
    historical = ArchiveBackedHistoricalChain(
        fixture.chain_id,
        fixture.chain,
        fixture.archives,
    )
    snapshot = historical.snapshot_at(
        fixture.cutoff_root
    )
    assert len(snapshot) == 6
    assert historical.verify_root(
        fixture.cutoff_root
    )
    assert historical.root_is_ancestor(
        fixture.cutoff_root
    )


def test_journal_capacity_is_reclaimed_after_floor_activates():
    backend = InMemoryFencedStore()
    floors = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
    )
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=4,
        clock=lambda: 1.0,
        hot_floor_store=floors,
        hot_floor_chain_id="journal",
    )
    events = append_events(journal, 4)
    with pytest.raises(RuntimeError, match="capacity"):
        append_events(journal, 1, start=4)
    floors.advance(
        chain_id="journal",
        sequence=2,
        root_hash=events[1].event_hash,
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    for event in reversed(events[:2]):
        record = backend.get(
            "journal",
            journal._event_key(event.event_hash),
        )
        backend.delete(
            "journal",
            journal._event_key(event.event_hash),
            expected_revision=record.revision,
        )
    assert journal.verify()
    append_events(journal, 2, start=4)
    assert journal.hot_length() == 4
    with pytest.raises(RuntimeError, match="capacity"):
        append_events(journal, 1, start=6)


def test_receipt_capacity_is_reclaimed_after_floor_activates():
    backend = InMemoryFencedStore()
    floors = DurableHotFloorStore(
        backend,
        signer("floor", b"f"),
    )
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=4,
        hot_floor_store=floors,
        hot_floor_chain_id="receipts",
    )
    items = tuple(
        chain.append(receipt(i))
        for i in range(4)
    )
    with pytest.raises(RuntimeError, match="capacity"):
        chain.append(receipt(4))
    floors.advance(
        chain_id="receipts",
        sequence=2,
        root_hash=items[1].receipt_hash,
        archive_id="archive",
        archive_manifest_digest=fp("archive"),
        compaction_certificate_id=fp("certificate"),
        pruning_authorization_id=fp("authorization"),
        operation_id=fp("operation"),
        fencing_token=1,
    )
    for item in reversed(items[:2]):
        record = backend.get(
            "receipts",
            chain._node_key(item.receipt_hash),
        )
        backend.delete(
            "receipts",
            chain._node_key(item.receipt_hash),
            expected_revision=record.revision,
        )
    assert chain.verify()
    chain.append(receipt(4))
    chain.append(receipt(5))
    assert chain.hot_length() == 4
    with pytest.raises(RuntimeError, match="capacity"):
        chain.append(receipt(6))


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_authorization_is_explicitly_destructive(kind):
    fixture = Fixture(kind=kind)
    auth = fixture.authorization
    assert auth.destructive_action_authorized
    assert auth.authorization.destructive_action_authorized
    assert not fixture.certificate.destructive_action_authorized
    assert (
        auth.signature.metadata["authority"]
        == "destructive-hot-tier-pruning"
    )
    report = fixture.authorization_store.require_current(
        auth,
        fixture.retention,
        fixture.chain,
    )
    assert report.allowed
    assert report.destructive_action_authorized


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_authorization_binds_exact_cutoff_archive_and_head(kind):
    fixture = Fixture(kind=kind)
    auth = fixture.authorization.authorization
    cert = fixture.certificate.certificate
    assert auth.chain_id == fixture.chain_id
    assert auth.certificate_id == cert.certificate_id
    assert auth.certificate_digest == cert.digest
    assert auth.current_sequence == cert.current_sequence
    assert auth.current_root == cert.current_root
    assert auth.cutoff_sequence == cert.cutoff_sequence
    assert auth.cutoff_root == cert.cutoff_root
    assert auth.archive_id == cert.archive_id
    assert (
        auth.archive_manifest_digest
        == cert.archive_manifest_digest
    )
    assert (
        auth.protected_roots_digest
        == cert.protected_roots_digest
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_chain_growth_stales_pruning_authorization(kind):
    fixture = Fixture(kind=kind)
    if kind == "journal":
        append_events(
            fixture.chain,
            1,
            start=8,
        )
    else:
        fixture.chain.append(receipt(8))
    report = fixture.authorization_store.inspect(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert not report.current
    assert not report.allowed


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_expired_pruning_authorization_is_rejected(kind):
    fixture = Fixture(kind=kind)
    fixture.now[0] = 431.0
    report = fixture.authorization_store.inspect(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert report.expired
    assert not report.allowed
    with pytest.raises(
        DurablePruningAuthorizationError,
        match="expired",
    ):
        fixture.authorization_store.require_current(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_executor_prunes_authorized_prefix(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert result.ok
    assert result.operation.phase is DurablePruningPhase.COMPLETE
    assert result.operation.deleted_items == 6
    assert result.operation.next_delete_index == -1
    assert result.floor.floor.sequence == 6
    assert fixture.chain.hot_length() == 2
    assert fixture.chain.verify()
    assert fixture.chain.snapshot() == fixture.later

    for sequence in range(1, 7):
        item = result.manifest.items[sequence - 1]
        assert fixture.backend.get(
            fixture.chain.namespace,
            item.node_key,
        ) is None
        assert fixture.backend.get(
            fixture.chain.namespace,
            item.sequence_key,
        ) is None
        if kind == "receipts":
            assert fixture.backend.get(
                fixture.chain.namespace,
                item.receipt_index_key,
            ) is None


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_executor_is_idempotent_after_completion(kind):
    fixture = Fixture(kind=kind)
    first = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    second = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert second.operation == first.operation
    assert second.manifest == first.manifest
    assert second.floor == first.floor
    assert second.ok


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_executor_preserves_archive_history_after_pruning(kind):
    fixture = Fixture(kind=kind)
    fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    historical = ArchiveBackedHistoricalChain(
        fixture.chain_id,
        fixture.chain,
        fixture.archives,
    )
    assert len(
        historical.snapshot_at(
            fixture.cutoff_root
        )
    ) == 6
    assert historical.verify_root(
        fixture.cutoff_root
    )


class FailDeleteOnceBackend(InMemoryFencedStore):
    def __init__(self):
        super().__init__()
        self.fail_enabled = False
        self.fail_after = 1
        self.calls = 0
        self.failed = False

    def delete(
        self,
        namespace,
        key,
        *,
        expected_revision,
    ):
        if self.fail_enabled and not self.failed:
            self.calls += 1
            if self.calls > self.fail_after:
                self.failed = True
                raise RuntimeError(
                    "synthetic pruning crash"
                )
        return super().delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_resume_after_crash_during_deletion(kind):
    backend = FailDeleteOnceBackend()
    fixture = Fixture(
        kind=kind,
        backend=backend,
    )
    backend.fail_enabled = True
    with pytest.raises(
        RuntimeError,
        match="synthetic pruning crash",
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )

    operation_id = fixture.executor.derive_operation_id(
        fixture.authorization.authorization_id,
        previous_floor_sequence=0,
        previous_floor_root="0" * 64,
    )
    partial = fixture.executor.operation(
        operation_id
    )
    assert partial is not None
    assert partial.phase is DurablePruningPhase.DELETING
    assert fixture.chain.hot_floor().sequence == 6

    backend.fail_enabled = False
    result = fixture.executor.resume(
        operation_id,
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert result.ok
    assert result.operation.phase is DurablePruningPhase.COMPLETE
    assert fixture.chain.verify()
    assert fixture.chain.snapshot() == fixture.later


def _archive_record_key(fixture):
    return fixture.archives._archive_key(
        fixture.authorization.authorization.archive_id
    )


def _delete_archive_record(fixture):
    key = _archive_record_key(fixture)
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    assert record is not None
    fixture.backend.delete(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
    )


def _delete_archived_node(
    fixture,
    item,
):
    key = fixture.archives._node_key(
        fixture.chain_id,
        item.node_hash,
    )
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    assert record is not None
    fixture.backend.delete(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
    )


def _hot_node_presence(
    fixture,
    manifest,
):
    return tuple(
        fixture.backend.get(
            fixture.chain.namespace,
            item.node_key,
        )
        is not None
        for item in manifest.items
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_archive_record_loss_before_execute_blocks_floor_and_marks_manual_review(
    kind,
):
    fixture = Fixture(kind=kind)
    manifest, operation = fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    before = _hot_node_presence(
        fixture,
        manifest,
    )
    _delete_archive_record(fixture)

    with pytest.raises(
        DurablePruningManualReview,
        match="bound archive is not recoverable",
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )

    current = fixture.executor.operation(
        operation.operation_id
    )
    assert current is not None
    assert (
        current.phase
        is DurablePruningPhase.MANUAL_REVIEW
    )
    assert fixture.chain.hot_floor().sequence == 0
    assert _hot_node_presence(
        fixture,
        manifest,
    ) == before
    assert all(before)


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_archive_node_loss_before_execute_blocks_destructive_boundary(
    kind,
):
    fixture = Fixture(kind=kind)
    manifest, operation = fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    target = manifest.items[-1]
    _delete_archived_node(
        fixture,
        target,
    )
    before = _hot_node_presence(
        fixture,
        manifest,
    )

    with pytest.raises(
        DurablePruningManualReview,
        match="bound archive is not recoverable",
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )

    current = fixture.executor.operation(
        operation.operation_id
    )
    assert current is not None
    assert current.requires_manual_review
    assert fixture.chain.hot_floor().sequence == 0
    assert _hot_node_presence(
        fixture,
        manifest,
    ) == before


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_archive_record_digest_tamper_blocks_pruning_before_floor_commit(
    kind,
):
    fixture = Fixture(kind=kind)
    manifest, operation = fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    key = _archive_record_key(fixture)
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    assert record is not None
    assert isinstance(record.value, dict)
    tampered = dict(record.value)
    tampered["record_digest"] = "f" * 64
    fixture.backend.compare_and_swap(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )

    with pytest.raises(
        DurablePruningManualReview,
        match="bound archive is not recoverable",
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )

    current = fixture.executor.operation(
        operation.operation_id
    )
    assert current is not None
    assert current.requires_manual_review
    assert fixture.chain.hot_floor().sequence == 0
    assert all(
        _hot_node_presence(
            fixture,
            manifest,
        )
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_per_item_archive_guard_blocks_delete_after_floor_commit(
    kind,
    monkeypatch,
):
    fixture = Fixture(kind=kind)
    manifest, operation = fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    before = _hot_node_presence(
        fixture,
        manifest,
    )

    original_guard = (
        fixture.executor
        ._require_archive_recoverability
    )
    original_get_node = (
        fixture.archives.get_node
    )
    armed = {"value": False}

    def guard_then_arm(bound_manifest):
        stored = original_guard(
            bound_manifest
        )
        armed["value"] = True
        return stored

    def fail_after_guard(
        chain_id,
        node_hash,
    ):
        if armed["value"]:
            raise DurableArchiveStoreError(
                "synthetic archive read loss"
            )
        return original_get_node(
            chain_id,
            node_hash,
        )

    monkeypatch.setattr(
        fixture.executor,
        "_require_archive_recoverability",
        guard_then_arm,
    )
    monkeypatch.setattr(
        fixture.archives,
        "get_node",
        fail_after_guard,
    )

    with pytest.raises(
        DurablePruningManualReview,
        match="archived pruning item is unreadable",
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )

    current = fixture.executor.operation(
        operation.operation_id
    )
    assert current is not None
    assert current.requires_manual_review
    assert (
        fixture.chain.hot_floor().sequence
        == fixture.cutoff_sequence
    )
    assert _hot_node_presence(
        fixture,
        manifest,
    ) == before
    assert all(before)


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_resume_after_partial_delete_stops_when_archive_is_lost(
    kind,
):
    backend = FailDeleteOnceBackend()
    fixture = Fixture(
        kind=kind,
        backend=backend,
    )
    manifest, operation = fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )

    backend.fail_enabled = True
    with pytest.raises(
        RuntimeError,
        match="synthetic pruning crash",
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )

    partial = fixture.executor.operation(
        operation.operation_id
    )
    assert partial is not None
    assert (
        partial.phase
        is DurablePruningPhase.DELETING
    )
    assert (
        fixture.chain.hot_floor().sequence
        == fixture.cutoff_sequence
    )
    before_resume = _hot_node_presence(
        fixture,
        manifest,
    )
    assert not all(before_resume)

    backend.fail_enabled = False
    remaining = tuple(
        item
        for item, present in zip(
            manifest.items,
            before_resume,
        )
        if present
    )
    assert remaining
    _delete_archived_node(
        fixture,
        remaining[-1],
    )

    with pytest.raises(
        DurablePruningManualReview,
        match="bound archive is not recoverable",
    ):
        fixture.executor.resume(
            operation.operation_id,
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )

    after_resume = _hot_node_presence(
        fixture,
        manifest,
    )
    assert after_resume == before_resume
    current = fixture.executor.operation(
        operation.operation_id
    )
    assert current is not None
    assert current.requires_manual_review


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_executor_archive_guard_is_bound_to_authorization_planner_repository(
    kind,
):
    fixture = Fixture(kind=kind)
    assert (
        fixture.executor.archives
        is fixture.archives
    )
    fresh = DurablePruningExecutor(
        fixture.backend,
        fixture.authorization_store,
        fixture.floor_store,
        namespace=f"{kind}-fresh-archive-guard",
    )
    assert fresh.archives is fixture.archives


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_successful_pruning_still_reverifies_archive_after_delete(
    kind,
    monkeypatch,
):
    fixture = Fixture(kind=kind)
    calls = {"count": 0}
    original = (
        fixture.executor
        ._require_archive_recoverability
    )

    def counted(manifest):
        calls["count"] += 1
        return original(manifest)

    monkeypatch.setattr(
        fixture.executor,
        "_require_archive_recoverability",
        counted,
    )
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert result.ok
    assert calls["count"] >= 2
    assert fixture.chain.verify()


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_prepare_is_non_destructive(kind):
    fixture = Fixture(kind=kind)
    before = fixture.chain.snapshot()
    manifest, operation = fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert manifest.delete_count == 6
    assert operation.phase is DurablePruningPhase.PREPARED
    assert fixture.chain.snapshot() == before
    assert fixture.chain.hot_floor().sequence == 0


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_manifest_binds_exact_immutable_revisions(kind):
    fixture = Fixture(kind=kind)
    manifest, _ = fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert manifest.current_sequence == 8
    assert manifest.cutoff_sequence == 6
    assert manifest.cutoff_root == fixture.cutoff_root
    assert tuple(
        item.sequence
        for item in manifest.items
    ) == tuple(range(1, 7))
    assert all(
        item.node_revision > 0
        for item in manifest.items
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_head_change_after_prepare_blocks_floor_commit(kind):
    fixture = Fixture(kind=kind)
    fixture.executor.prepare(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    if kind == "journal":
        append_events(
            fixture.chain,
            1,
            start=8,
        )
    else:
        fixture.chain.append(receipt(8))
    with pytest.raises(
        DurablePruningManualReview,
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )
    assert fixture.chain.hot_floor().sequence == 0


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_chain_must_use_executor_floor_store(kind):
    fixture = Fixture(kind=kind)
    other_floors = DurableHotFloorStore(
        fixture.backend,
        fixture.floor_signer,
        namespace="other-floors",
    )
    other_executor = DurablePruningExecutor(
        fixture.backend,
        fixture.authorization_store,
        other_floors,
        namespace="other-pruning",
    )
    with pytest.raises(
        DurablePruningError,
        match="hot floor store",
    ):
        other_executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )


def test_receipt_pruning_removes_old_receipt_index_but_keeps_new():
    fixture = Fixture(kind="receipts")
    old_id = fixture.first[0].receipt.receipt_id
    new_id = fixture.later[0].receipt.receipt_id
    fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert fixture.chain.find_by_receipt_id(
        old_id
    ) is None
    assert fixture.chain.require_receipt(
        new_id
    ).committed


def test_journal_append_continues_monotonic_sequence_after_pruning():
    fixture = Fixture(kind="journal")
    fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    event = append_events(
        fixture.chain,
        1,
        start=8,
    )[0]
    assert event.sequence == 9
    assert fixture.chain.verify()
    assert fixture.chain.hot_length() == 3


def test_receipt_append_continues_monotonic_sequence_after_pruning():
    fixture = Fixture(kind="receipts")
    fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    item = fixture.chain.append(
        receipt(8)
    )
    assert item.sequence == 9
    assert fixture.chain.verify()
    assert fixture.chain.hot_length() == 3


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_operation_and_manifest_survive_fresh_executor(kind):
    fixture = Fixture(kind=kind)
    first = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    fresh = DurablePruningExecutor(
        fixture.backend,
        fixture.authorization_store,
        fixture.floor_store,
        namespace=f"{kind}-pruning",
        clock=lambda: fixture.now[0],
    )
    operation = fresh.operation(
        first.operation.operation_id
    )
    manifest = fresh.manifest(
        first.operation.operation_id
    )
    assert operation == first.operation
    assert manifest == first.manifest


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_floor_metadata_binds_pruning_operation(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    floor = result.floor.floor
    assert floor.operation_id == result.operation.operation_id
    assert (
        floor.pruning_authorization_id
        == fixture.authorization.authorization_id
    )
    assert (
        floor.compaction_certificate_id
        == fixture.certificate.certificate_id
    )
    assert floor.archive_id == fixture.archive.manifest.archive_id


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_result_serializes_authority_and_progress(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    data = result.to_dict()
    assert data["ok"] is True
    assert data["operation"]["phase"] == "complete"
    assert data["manifest"]["delete_count"] if "delete_count" in data["manifest"] else True
    assert data["floor"]["floor"]["sequence"] == 6


def _history_store(clock=lambda: 10.0):
    backend = InMemoryFencedStore()
    store = DurableHotFloorStore(
        backend,
        signer("history-floor", b"h", clock=clock),
        namespace="history-floors",
        clock=clock,
    )
    return backend, store


def _advance_history_floor(
    store,
    *,
    sequence,
    root,
    suffix,
    fencing_token,
    previous_sequence=None,
    previous_root="",
):
    return store.advance(
        chain_id="journal",
        sequence=sequence,
        root_hash=root,
        archive_id=f"archive-{suffix}",
        archive_manifest_digest=fp(f"archive-{suffix}"),
        compaction_certificate_id=fp(f"certificate-{suffix}"),
        pruning_authorization_id=fp(f"authorization-{suffix}"),
        operation_id=fp(f"operation-{suffix}"),
        fencing_token=fencing_token,
        expected_previous_sequence=previous_sequence,
        expected_previous_root=previous_root,
    )


def test_floor_history_persists_current_floor_by_id():
    _, store = _history_store()
    item = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    assert store.get(item.floor.floor_id) == item


def test_floor_history_persists_current_floor_by_sequence():
    _, store = _history_store()
    item = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    assert store.floor_at("journal", 3) == item


def test_displaced_floor_remains_available_by_id():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    second = _advance_history_floor(
        store,
        sequence=5,
        root=fp("root-5"),
        suffix="two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=fp("root-3"),
    )
    assert store.current("journal") == second
    assert store.get(first.floor.floor_id) == first


def test_displaced_floor_remains_available_by_sequence():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    _advance_history_floor(
        store,
        sequence=5,
        root=fp("root-5"),
        suffix="two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=fp("root-3"),
    )
    assert store.floor_at("journal", 3) == first


def test_multiple_floor_history_survives_fresh_reader():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    second = _advance_history_floor(
        store,
        sequence=5,
        root=fp("root-5"),
        suffix="two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=fp("root-3"),
    )
    third = _advance_history_floor(
        store,
        sequence=7,
        root=fp("root-7"),
        suffix="three",
        fencing_token=3,
        previous_sequence=5,
        previous_root=fp("root-5"),
    )
    fresh = DurableHotFloorStore(
        backend,
        store.signer,
        namespace="history-floors",
        clock=lambda: 10.0,
    )
    assert fresh.get(first.floor.floor_id) == first
    assert fresh.get(second.floor.floor_id) == second
    assert fresh.get(third.floor.floor_id) == third
    assert fresh.floor_at("journal", 3) == first
    assert fresh.floor_at("journal", 5) == second
    assert fresh.floor_at("journal", 7) == third


def test_floor_history_preserves_previous_floor_binding():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    second = _advance_history_floor(
        store,
        sequence=6,
        root=fp("root-6"),
        suffix="two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=fp("root-3"),
    )
    historical = store.get(second.floor.floor_id)
    assert historical.floor.previous_sequence == first.floor.sequence
    assert historical.floor.previous_root_hash == first.floor.root_hash


def test_same_sequence_retry_does_not_duplicate_history_authority():
    backend, store = _history_store()
    kwargs = dict(
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    first = _advance_history_floor(store, **kwargs)
    second = _advance_history_floor(store, **kwargs)
    assert second == first
    history = backend.get(
        store.namespace,
        store._history_key(first.floor.floor_id),
    )
    index = backend.get(
        store.namespace,
        store._sequence_key("journal", 3),
    )
    assert history is not None
    assert index is not None


def test_floor_history_missing_sequence_returns_none():
    _, store = _history_store()
    _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    assert store.floor_at("journal", 2) is None


def test_floor_history_missing_id_returns_none():
    _, store = _history_store()
    assert store.get(fp("missing-floor")) is None


def test_floor_at_repairs_missing_current_sequence_index():
    backend, store = _history_store()
    item = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    key = store._sequence_key("journal", 3)
    record = backend.get(store.namespace, key)
    backend.delete(
        store.namespace,
        key,
        expected_revision=record.revision,
    )
    assert backend.get(store.namespace, key) is None
    repaired = store.floor_at("journal", 3)
    assert repaired == item
    assert backend.get(store.namespace, key) is not None


def test_floor_at_repairs_missing_current_history_record():
    backend, store = _history_store()
    item = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    history_key = store._history_key(item.floor.floor_id)
    index_key = store._sequence_key("journal", 3)
    history_record = backend.get(
        store.namespace,
        history_key,
    )
    index_record = backend.get(
        store.namespace,
        index_key,
    )
    backend.delete(
        store.namespace,
        history_key,
        expected_revision=history_record.revision,
    )
    backend.delete(
        store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )
    repaired = store.floor_at("journal", 3)
    assert repaired == item
    assert backend.get(store.namespace, history_key) is not None
    assert backend.get(store.namespace, index_key) is not None


def test_displacing_floor_repairs_previous_history_before_cas():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    history_key = store._history_key(first.floor.floor_id)
    index_key = store._sequence_key("journal", 3)
    history_record = backend.get(store.namespace, history_key)
    index_record = backend.get(store.namespace, index_key)
    backend.delete(
        store.namespace,
        history_key,
        expected_revision=history_record.revision,
    )
    backend.delete(
        store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )
    _advance_history_floor(
        store,
        sequence=5,
        root=fp("root-5"),
        suffix="two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=fp("root-3"),
    )
    assert store.get(first.floor.floor_id) == first
    assert store.floor_at("journal", 3) == first


def test_floor_history_signature_tamper_is_rejected():
    backend, store = _history_store()
    item = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    key = store._history_key(item.floor.floor_id)
    record = backend.get(store.namespace, key)
    payload = dict(record.value)
    floor = dict(payload["floor"])
    floor["archive_id"] = "tampered-archive"
    payload["floor"] = floor
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="signature",
    ):
        store.get(item.floor.floor_id)


def test_floor_history_index_wrong_value_type_is_rejected():
    backend, store = _history_store()
    item = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    key = store._sequence_key("journal", 3)
    record = backend.get(store.namespace, key)
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(
        (DurableHotFloorError, KeyError),
    ):
        store.floor_at("journal", 3)
    assert item.floor.sequence == 3


def test_floor_history_index_floor_id_substitution_is_rejected():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    second = _advance_history_floor(
        store,
        sequence=5,
        root=fp("root-5"),
        suffix="two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=fp("root-3"),
    )
    key = store._sequence_key("journal", 3)
    record = backend.get(store.namespace, key)
    payload = dict(record.value)
    payload["floor_id"] = second.floor.floor_id
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="index/content",
    ):
        store.floor_at("journal", 3)
    assert store.get(first.floor.floor_id) == first


def test_floor_history_index_root_substitution_is_rejected():
    backend, store = _history_store()
    _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    key = store._sequence_key("journal", 3)
    record = backend.get(store.namespace, key)
    payload = dict(record.value)
    payload["root_hash"] = fp("other-root")
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="index/content",
    ):
        store.floor_at("journal", 3)


def test_floor_history_sequence_index_conflict_blocks_later_advance():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    key = store._sequence_key("journal", 3)
    record = backend.get(store.namespace, key)
    payload = dict(record.value)
    payload["floor_id"] = fp("foreign-floor")
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="different floor",
    ):
        _advance_history_floor(
            store,
            sequence=5,
            root=fp("root-5"),
            suffix="two",
            fencing_token=2,
            previous_sequence=3,
            previous_root=fp("root-3"),
        )
    assert store.current("journal") == first


@pytest.mark.parametrize("sequence", [0, -1, True])
def test_floor_history_sequence_validation(sequence):
    _, store = _history_store()
    with pytest.raises(ValueError, match="positive"):
        store.floor_at("journal", sequence)


def test_floor_history_chain_validation():
    _, store = _history_store()
    with pytest.raises(ValueError, match="chain_id"):
        store.floor_at("", 1)


def test_floor_history_id_validation():
    _, store = _history_store()
    with pytest.raises(ValueError, match="64-character"):
        store.get("bad")


def test_floor_history_is_namespaced():
    backend = InMemoryFencedStore()
    first = DurableHotFloorStore(
        backend,
        signer("first-history", b"1"),
        namespace="first-history",
        clock=lambda: 10.0,
    )
    second = DurableHotFloorStore(
        backend,
        signer("second-history", b"2"),
        namespace="second-history",
        clock=lambda: 10.0,
    )
    item = _advance_history_floor(
        first,
        sequence=3,
        root=fp("root-3"),
        suffix="one",
        fencing_token=1,
    )
    assert first.get(item.floor.floor_id) == item
    assert second.get(item.floor.floor_id) is None


def test_hot_floor_history_empty_chain_is_verified():
    _, store = _history_store()
    report = store.require_history("journal")
    assert report.ok
    assert report.floor_count == 0
    assert report.complete_to_genesis
    assert report.current_sequence == 0
    assert report.current_root == "0" * 64


def test_hot_floor_history_single_floor_reaches_genesis():
    _, store = _history_store()
    floor = _advance_history_floor(
        store,
        sequence=3,
        root=fp("history-root-3"),
        suffix="history-one",
        fencing_token=1,
    )
    report = store.require_history("journal")
    assert report.ok
    assert report.floor_count == 1
    assert report.floors == (floor,)
    assert report.oldest_sequence == 3
    assert report.newest_sequence == 3


def test_hot_floor_history_multi_floor_order_is_oldest_to_newest():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("history-root-3"),
        suffix="history-one",
        fencing_token=1,
    )
    second = _advance_history_floor(
        store,
        sequence=5,
        root=fp("history-root-5"),
        suffix="history-two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=first.floor.root_hash,
    )
    third = _advance_history_floor(
        store,
        sequence=9,
        root=fp("history-root-9"),
        suffix="history-three",
        fencing_token=3,
        previous_sequence=5,
        previous_root=second.floor.root_hash,
    )
    report = store.require_history("journal")
    assert report.floors == (
        first,
        second,
        third,
    )
    assert report.oldest_sequence == 3
    assert report.newest_sequence == 9
    assert report.current_floor_id == third.floor.floor_id


def test_hot_floor_history_fresh_reader_reconstructs_all_floors():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=2,
        root=fp("fresh-history-2"),
        suffix="fresh-one",
        fencing_token=1,
    )
    second = _advance_history_floor(
        store,
        sequence=6,
        root=fp("fresh-history-6"),
        suffix="fresh-two",
        fencing_token=2,
        previous_sequence=2,
        previous_root=first.floor.root_hash,
    )
    fresh = DurableHotFloorStore(
        backend,
        store.signer,
        namespace="history-floors",
        clock=lambda: 20.0,
    )
    report = fresh.require_history("journal")
    assert report.floors == (first, second)
    assert report.ok


def test_hot_floor_history_missing_middle_floor_is_incomplete():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=2,
        root=fp("missing-middle-2"),
        suffix="missing-one",
        fencing_token=1,
    )
    _advance_history_floor(
        store,
        sequence=6,
        root=fp("missing-middle-6"),
        suffix="missing-two",
        fencing_token=2,
        previous_sequence=2,
        previous_root=first.floor.root_hash,
    )
    history_key = store._history_key(
        first.floor.floor_id
    )
    index_key = store._sequence_key(
        "journal",
        first.floor.sequence,
    )
    history_record = backend.get(
        store.namespace,
        history_key,
    )
    index_record = backend.get(
        store.namespace,
        index_key,
    )
    backend.delete(
        store.namespace,
        history_key,
        expected_revision=history_record.revision,
    )
    backend.delete(
        store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )
    report = store.inspect_history("journal")
    assert not report.ok
    assert not report.complete_to_genesis
    assert any(
        "missing" in issue
        for issue in report.issues
    )
    with pytest.raises(
        DurableHotFloorError,
        match="missing",
    ):
        store.require_history("journal")


def test_hot_floor_history_bound_is_fail_closed():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=2,
        root=fp("bound-2"),
        suffix="bound-one",
        fencing_token=1,
    )
    _advance_history_floor(
        store,
        sequence=4,
        root=fp("bound-4"),
        suffix="bound-two",
        fencing_token=2,
        previous_sequence=2,
        previous_root=first.floor.root_hash,
    )
    report = store.inspect_history(
        "journal",
        max_floors=1,
    )
    assert not report.ok
    assert any(
        "bound" in issue
        for issue in report.issues
    )


@pytest.mark.parametrize("maximum", [0, -1, True])
def test_hot_floor_history_bound_validation(maximum):
    _, store = _history_store()
    with pytest.raises(
        ValueError,
        match="max_floors",
    ):
        store.inspect_history(
            "journal",
            max_floors=maximum,
        )


def test_hot_floor_history_report_digest_is_stable():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("digest-root-3"),
        suffix="digest-one",
        fencing_token=1,
    )
    _advance_history_floor(
        store,
        sequence=7,
        root=fp("digest-root-7"),
        suffix="digest-two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=first.floor.root_hash,
    )
    one = store.require_history("journal")
    two = store.require_history("journal")
    assert one == two
    assert one.digest == two.digest
    assert one.to_dict()["digest"] == one.digest


def test_hot_floor_advance_rejects_non_increasing_fencing_token():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("fence-root-3"),
        suffix="fence-one",
        fencing_token=5,
    )
    with pytest.raises(
        DurableHotFloorError,
        match="fencing token must increase",
    ):
        _advance_history_floor(
            store,
            sequence=6,
            root=fp("fence-root-6"),
            suffix="fence-two",
            fencing_token=5,
            previous_sequence=3,
            previous_root=first.floor.root_hash,
        )


def test_hot_floor_advance_accepts_strictly_increasing_fencing_token():
    _, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("fence-ok-3"),
        suffix="fence-ok-one",
        fencing_token=5,
    )
    second = _advance_history_floor(
        store,
        sequence=6,
        root=fp("fence-ok-6"),
        suffix="fence-ok-two",
        fencing_token=6,
        previous_sequence=3,
        previous_root=first.floor.root_hash,
    )
    assert second.floor.fencing_token == 6
    assert store.require_history("journal").ok


def test_hot_floor_history_detects_sequence_index_corruption():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("index-corrupt-3"),
        suffix="index-corrupt-one",
        fencing_token=1,
    )
    _advance_history_floor(
        store,
        sequence=6,
        root=fp("index-corrupt-6"),
        suffix="index-corrupt-two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=first.floor.root_hash,
    )
    key = store._sequence_key("journal", 3)
    record = backend.get(store.namespace, key)
    payload = dict(record.value)
    payload["floor_id"] = fp("wrong-history-floor")
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    report = store.inspect_history("journal")
    assert not report.ok
    assert any(
        "lookup raised" in issue
        for issue in report.issues
    )


def test_hot_floor_history_detects_signed_history_tamper():
    backend, store = _history_store()
    first = _advance_history_floor(
        store,
        sequence=3,
        root=fp("signed-corrupt-3"),
        suffix="signed-corrupt-one",
        fencing_token=1,
    )
    _advance_history_floor(
        store,
        sequence=6,
        root=fp("signed-corrupt-6"),
        suffix="signed-corrupt-two",
        fencing_token=2,
        previous_sequence=3,
        previous_root=first.floor.root_hash,
    )
    key = store._history_key(first.floor.floor_id)
    record = backend.get(store.namespace, key)
    payload = dict(record.value)
    floor_payload = dict(payload["floor"])
    floor_payload["operation_id"] = fp("tampered-operation")
    payload["floor"] = floor_payload
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    report = store.inspect_history("journal")
    assert not report.ok
    assert any(
        "lookup raised" in issue
        for issue in report.issues
    )

@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_emits_signed_destruction_record(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert result.destruction_record_id
    assert result.destruction_record_digest
    stored = fixture.destruction_ledger.find_operation(
        fixture.chain_id,
        "pruning",
        result.operation.operation_id,
    )
    assert stored is not None
    assert stored.record_id == result.destruction_record_id
    assert stored.record.digest == result.destruction_record_digest
    assert stored.record.authority_id == fixture.authorization.authorization_id
    assert stored.record.authority_digest == fixture.authorization.authorization.digest
    assert stored.record.manifest_digest == result.manifest.digest
    assert stored.record.archive_id == result.manifest.archive_id
    assert (
        stored.record.archive_manifest_digest
        == result.manifest.archive_manifest_digest
    )
    assert stored.record.post_verified
    assert stored.record.fencing_token == result.operation.fencing_token
    assert fixture.destruction_ledger.require_verified(
        fixture.chain_id
    ).ok


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_destruction_record_binds_floor_transition(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    record = fixture.destruction_ledger.find_operation(
        fixture.chain_id,
        "pruning",
        result.operation.operation_id,
    ).record
    assert (
        record.before_floor_sequence
        == result.manifest.previous_floor_sequence
    )
    assert (
        record.before_floor_root
        == result.manifest.previous_floor_root
    )
    assert (
        record.after_floor_sequence
        == result.manifest.cutoff_sequence
    )
    assert (
        record.after_floor_root
        == result.manifest.cutoff_root
    )
    assert record.after_sequence >= result.manifest.current_sequence


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_destruction_items_cover_deleted_backend_records(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    record = fixture.destruction_ledger.find_operation(
        fixture.chain_id,
        "pruning",
        result.operation.operation_id,
    ).record
    keys = {
        item.backend_key
        for item in record.items
    }
    for manifest_item in result.manifest.items:
        assert manifest_item.node_key in keys
        if manifest_item.sequence_revision is not None:
            assert manifest_item.sequence_key in keys
        if (
            kind == "receipts"
            and manifest_item.receipt_index_revision is not None
        ):
            assert manifest_item.receipt_index_key in keys
    assert all(item.archived for item in record.items)
    assert record.deleted_count == len(record.items)
    assert record.already_absent_count == 0


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_result_serializes_destruction_evidence(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    data = result.to_dict()
    assert (
        data["destruction_record_id"]
        == result.destruction_record_id
    )
    assert (
        data["destruction_record_digest"]
        == result.destruction_record_digest
    )
    assert len(data["destruction_record_id"]) == 64


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_retry_reuses_same_destruction_record(kind):
    fixture = Fixture(kind=kind)
    first = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    second = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert second.destruction_record_id == first.destruction_record_id
    assert (
        second.destruction_record_digest
        == first.destruction_record_digest
    )
    assert len(
        fixture.destruction_ledger.snapshot(
            fixture.chain_id
        )
    ) == 1


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_retry_after_chain_growth_reuses_original_destruction_record(kind):
    fixture = Fixture(kind=kind)
    first = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    if kind == "journal":
        append_events(
            fixture.chain,
            1,
            start=100,
        )
    else:
        fixture.chain.append(
            receipt(100)
        )
    assert fixture.chain.head().sequence > first.manifest.current_sequence
    second = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert second.destruction_record_id == first.destruction_record_id
    stored = fixture.destruction_ledger.find_operation(
        fixture.chain_id,
        "pruning",
        first.operation.operation_id,
    )
    assert stored.record.after_sequence == first.manifest.current_sequence
    assert (
        stored.record.after_root
        == first.manifest.current_root
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_fresh_pruning_executor_reuses_destruction_ledger_record(kind):
    fixture = Fixture(kind=kind)
    first = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    fresh_ledger = DurableDestructionLedger(
        fixture.backend,
        signer(
            "destruction",
            b"d",
            clock=lambda: fixture.now[0],
        ),
        namespace=f"{kind}-destruction",
        clock=lambda: fixture.now[0],
    )
    fresh = DurablePruningExecutor(
        fixture.backend,
        fixture.authorization_store,
        fixture.floor_store,
        destruction_ledger=fresh_ledger,
        namespace=f"{kind}-pruning",
        max_items=100,
        clock=lambda: fixture.now[0],
    )
    second = fresh.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    assert second.destruction_record_id == first.destruction_record_id
    assert fresh_ledger.require_verified(
        fixture.chain_id
    ).ok


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_destruction_index_repairs_after_loss(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    stored = fixture.destruction_ledger.find_operation(
        fixture.chain_id,
        "pruning",
        result.operation.operation_id,
    )
    key = fixture.destruction_ledger._operation_index_key(
        stored.operation_key
    )
    record = fixture.backend.get(
        fixture.destruction_ledger.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.destruction_ledger.namespace,
        key,
        expected_revision=record.revision,
    )
    repaired = fixture.destruction_ledger.find_operation(
        fixture.chain_id,
        "pruning",
        result.operation.operation_id,
    )
    assert repaired.record_id == result.destruction_record_id
    assert fixture.backend.get(
        fixture.destruction_ledger.namespace,
        key,
    ) is not None


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_pruning_retry_fails_closed_on_destruction_signature_tamper(kind):
    fixture = Fixture(kind=kind)
    result = fixture.executor.execute(
        fixture.authorization,
        fixture.retention,
        fixture.chain,
    )
    key = fixture.destruction_ledger._record_key(
        result.destruction_record_id
    )
    stored = fixture.backend.get(
        fixture.destruction_ledger.namespace,
        key,
    )
    raw = dict(stored.value)
    signature = dict(raw["signature"])
    signature["signature"] = "f" * 64
    raw["signature"] = signature
    fixture.backend.compare_and_swap(
        fixture.destruction_ledger.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    with pytest.raises(
        DurablePruningManualReview,
        match="destruction evidence",
    ):
        fixture.executor.execute(
            fixture.authorization,
            fixture.retention,
            fixture.chain,
        )


def test_pruning_executor_rejects_wrong_destruction_ledger_type():
    fixture = Fixture(kind="journal")
    with pytest.raises(
        TypeError,
        match="destruction_ledger",
    ):
        DurablePruningExecutor(
            fixture.backend,
            fixture.authorization_store,
            fixture.floor_store,
            destruction_ledger=object(),
        )
