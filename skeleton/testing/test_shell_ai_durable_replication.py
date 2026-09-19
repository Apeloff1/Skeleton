"""Durable evidence replication and promotion tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicationReport,
    DurableChainReplicator,
    DurableEvidenceReplicaManager,
    DurableEvidenceReplicationReport,
    DurableReplicaState,
    DurableReplicationBatch,
    DurableReplicationError,
    DurableReplicationPolicy,
    DurableReplicationRun,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def make_journal(
    count: int,
    *,
    namespace: str,
):
    backend = InMemoryFencedStore()
    time = {"value": 1.0}

    def clock():
        value = time["value"]
        time["value"] += 1.0
        return value

    chain = DistributedAIDecisionJournal(
        backend,
        namespace=namespace,
        clock=clock,
    )
    for index in range(1, count + 1):
        chain.append(
            f"event.{index}",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
            summary=f"summary-{index}",
            data={"index": index},
        )
    return backend, chain


def make_receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(hex(index % 16)[2:]),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=index,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
        metadata={"index": index},
    )


def make_receipts(
    count: int,
    *,
    namespace: str,
):
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace=namespace,
    )
    for index in range(1, count + 1):
        chain.append(make_receipt(index))
    return backend, chain


def journal_replicator(
    source,
    target,
    *,
    batch=1024,
    max_batches=64,
):
    return DurableChainReplicator(
        "journal",
        source,
        target,
        policy=DurableReplicationPolicy(
            max_batch_items=batch,
            max_batches_per_run=max_batches,
        ),
    )


def receipt_replicator(
    source,
    target,
    *,
    batch=1024,
    max_batches=64,
):
    return DurableChainReplicator(
        "receipts",
        source,
        target,
        policy=DurableReplicationPolicy(
            max_batch_items=batch,
            max_batches_per_run=max_batches,
        ),
    )


def test_empty_journals_are_in_sync():
    _, source = make_journal(
        0,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.IN_SYNC
    assert report.in_sync
    assert not report.syncable
    assert report.source_sequence == 0
    assert report.target_sequence == 0
    assert report.lag_items == 0


def test_empty_receipt_chains_are_in_sync():
    _, source = make_receipts(
        0,
        namespace="source",
    )
    _, target = make_receipts(
        0,
        namespace="target",
    )
    report = receipt_replicator(
        source,
        target,
    ).inspect()
    assert report.in_sync
    assert report.state is DurableReplicaState.IN_SYNC


def test_lagging_empty_journal_target_is_syncable():
    _, source = make_journal(
        3,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.LAGGING
    assert report.syncable
    assert report.lag_items == 3
    assert report.next_sequence == 1


def test_lagging_empty_receipt_target_is_syncable():
    _, source = make_receipts(
        3,
        namespace="source",
    )
    _, target = make_receipts(
        0,
        namespace="target",
    )
    report = receipt_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.LAGGING
    assert report.lag_items == 3
    assert report.next_sequence == 1


def test_journal_sync_once_copies_one_bounded_batch():
    _, source = make_journal(
        5,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    replicator = journal_replicator(
        source,
        target,
        batch=2,
    )
    batch = replicator.sync_once()
    assert batch.transferred_items == 2
    assert batch.first_sequence == 1
    assert batch.last_sequence == 2
    assert not batch.completed
    assert target.length() == 2
    assert target.snapshot() == source.snapshot()[:2]


def test_receipt_sync_once_copies_one_bounded_batch():
    _, source = make_receipts(
        5,
        namespace="source",
    )
    _, target = make_receipts(
        0,
        namespace="target",
    )
    replicator = receipt_replicator(
        source,
        target,
        batch=2,
    )
    batch = replicator.sync_once()
    assert batch.transferred_items == 2
    assert target.length() == 2
    assert target.snapshot() == source.snapshot()[:2]


def test_journal_sync_catches_up_across_batches():
    _, source = make_journal(
        7,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    run = journal_replicator(
        source,
        target,
        batch=2,
    ).sync()
    assert run.completed
    assert run.transferred_items == 7
    assert len(run.batches) == 4
    assert target.snapshot() == source.snapshot()
    assert target.root_hash() == source.root_hash()


def test_receipt_sync_catches_up_across_batches():
    _, source = make_receipts(
        7,
        namespace="source",
    )
    _, target = make_receipts(
        0,
        namespace="target",
    )
    run = receipt_replicator(
        source,
        target,
        batch=3,
    ).sync()
    assert run.completed
    assert run.transferred_items == 7
    assert len(run.batches) == 3
    assert target.snapshot() == source.snapshot()


def test_replication_resume_from_partial_target():
    _, source = make_journal(
        6,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    target.restore_segment(
        source.snapshot()[:3]
    )
    run = journal_replicator(
        source,
        target,
        batch=2,
    ).sync()
    assert run.completed
    assert run.transferred_items == 3
    assert target.snapshot() == source.snapshot()


def test_receipt_replication_resume_from_partial_target():
    _, source = make_receipts(
        6,
        namespace="source",
    )
    _, target = make_receipts(
        0,
        namespace="target",
    )
    target.restore_segment(
        source.snapshot()[:4]
    )
    run = receipt_replicator(
        source,
        target,
        batch=1,
    ).sync()
    assert run.completed
    assert run.transferred_items == 2
    assert target.snapshot() == source.snapshot()


def test_sync_once_when_already_in_sync_is_noop():
    _, source = make_journal(
        2,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    target.restore_segment(
        source.snapshot()
    )
    batch = journal_replicator(
        source,
        target,
    ).sync_once()
    assert batch.transferred_items == 0
    assert batch.first_sequence is None
    assert batch.last_sequence is None
    assert batch.completed


def test_same_sequence_different_journal_root_is_diverged():
    _, source = make_journal(
        1,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    target.append(
        "different",
        session_id="different",
        intent_id="different",
        proposal_id="different",
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.DIVERGED
    assert not report.syncable
    assert "different roots" in report.reason


def test_same_sequence_different_receipt_root_is_diverged():
    _, source = make_receipts(
        1,
        namespace="source",
    )
    _, target = make_receipts(
        0,
        namespace="target",
    )
    target.append(
        replace(
            make_receipt(1),
            receipt_id="different",
            fingerprint=fp("f"),
        )
    )
    report = receipt_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.DIVERGED


def test_target_prefix_divergence_is_detected_before_sync():
    _, source = make_journal(
        4,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    target.append(
        "different",
        session_id="different",
        intent_id="different",
        proposal_id="different",
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.DIVERGED
    with pytest.raises(
        DurableReplicationError,
        match="not syncable",
    ):
        journal_replicator(
            source,
            target,
        ).sync_once()


def test_target_ahead_with_source_prefix_is_classified():
    _, source = make_journal(
        2,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    target.restore_segment(
        source.snapshot()
    )
    target.append(
        "target.extra",
        session_id="target",
        intent_id="target",
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.TARGET_AHEAD
    assert "exact prefix" in report.reason
    assert not report.syncable


def test_receipt_target_ahead_with_source_prefix_is_classified():
    _, source = make_receipts(
        2,
        namespace="source",
    )
    _, target = make_receipts(
        0,
        namespace="target",
    )
    target.restore_segment(
        source.snapshot()
    )
    target.append(
        make_receipt(3)
    )
    report = receipt_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.TARGET_AHEAD


def test_target_ahead_divergent_prefix_is_diverged():
    _, source = make_journal(
        1,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    target.append(
        "different",
        session_id="x",
        intent_id="x",
    )
    target.append(
        "extra",
        session_id="x",
        intent_id="x",
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.DIVERGED


def test_corrupt_source_is_rejected():
    backend, source = make_journal(
        2,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    terminal = source.snapshot()[-1]
    key = source._event_key(
        terminal.event_hash
    )
    record = backend.get(
        "source",
        key,
    )
    backend.compare_and_swap(
        "source",
        key,
        expected_revision=record.revision,
        value=replace(
            terminal,
            summary="tampered",
        ),
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.SOURCE_INVALID
    assert not report.source_valid


def test_corrupt_target_is_rejected():
    _, source = make_journal(
        3,
        namespace="source",
    )
    backend, target = make_journal(
        0,
        namespace="target",
    )
    target.restore_segment(
        source.snapshot()[:1]
    )
    first = target.snapshot()[0]
    key = target._event_key(
        first.event_hash
    )
    record = backend.get(
        "target",
        key,
    )
    backend.compare_and_swap(
        "target",
        key,
        expected_revision=record.revision,
        value=replace(
            first,
            summary="tampered",
        ),
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    assert report.state is DurableReplicaState.TARGET_INVALID
    assert not report.target_valid


class MissingHistorySource:
    def __init__(self, source):
        self.source = source

    def head(self):
        return self.source.head()

    def verify(self):
        return self.source.verify()

    def root_for_sequence(self, sequence):
        if sequence <= 1:
            return self.source.root_for_sequence(
                sequence
            )
        raise RuntimeError(
            "historical segment compacted"
        )

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        raise RuntimeError(
            "historical segment compacted"
        )


def test_history_unavailable_is_explicit():
    _, source = make_journal(
        3,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    report = journal_replicator(
        MissingHistorySource(source),
        target,
    ).inspect()
    assert report.state is DurableReplicaState.HISTORY_UNAVAILABLE
    assert not report.syncable


class InvalidVerifySource(MissingHistorySource):
    def verify(self):
        return False

    def root_for_sequence(self, sequence):
        return self.source.root_for_sequence(
            sequence
        )


def test_source_integrity_requirement_can_be_disabled_for_inspection():
    _, source = make_journal(
        1,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    policy = DurableReplicationPolicy(
        require_source_integrity=False,
    )
    replicator = DurableChainReplicator(
        "journal",
        InvalidVerifySource(source),
        target,
        policy=policy,
    )
    report = replicator.inspect()
    assert report.source_valid is False
    assert report.state in {
        DurableReplicaState.LAGGING,
        DurableReplicaState.HISTORY_UNAVAILABLE,
    }


def test_sync_run_can_stop_at_batch_limit():
    _, source = make_journal(
        10,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    replicator = journal_replicator(
        source,
        target,
        batch=2,
        max_batches=2,
    )
    run = replicator.sync()
    assert not run.completed
    assert run.transferred_items == 4
    assert len(run.batches) == 2
    assert run.final.state is DurableReplicaState.LAGGING


def test_sync_explicit_batch_limit():
    _, source = make_journal(
        8,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    replicator = journal_replicator(
        source,
        target,
        batch=2,
    )
    run = replicator.sync(
        max_batches=1
    )
    assert len(run.batches) == 1
    assert target.length() == 2
    assert not run.completed


@pytest.mark.parametrize(
    "value",
    [0, -1, True, 4097],
)
def test_sync_validates_explicit_batch_limit(value):
    _, source = make_journal(
        1,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    with pytest.raises(ValueError, match="max_batches"):
        journal_replicator(
            source,
            target,
        ).sync(max_batches=value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_batch_items": 0},
        {"max_batch_items": 65537},
        {"max_batch_items": True},
        {"max_batches_per_run": 0},
        {"max_batches_per_run": 4097},
        {"promotion_max_lag_items": -1},
        {"require_source_integrity": "yes"},
        {"require_target_integrity": 1},
    ],
)
def test_replication_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableReplicationPolicy(**kwargs)


def test_replication_policy_digest_is_stable():
    first = DurableReplicationPolicy(
        max_batch_items=10,
    )
    second = DurableReplicationPolicy(
        max_batch_items=10,
    )
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()


def test_replicator_surface_validation():
    _, target = make_journal(
        0,
        namespace="target",
    )
    with pytest.raises(TypeError, match="source"):
        DurableChainReplicator(
            "journal",
            object(),
            target,
        )
    _, source = make_journal(
        0,
        namespace="source",
    )
    with pytest.raises(TypeError, match="target"):
        DurableChainReplicator(
            "journal",
            source,
            object(),
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 129],
)
def test_replicator_chain_id_validation(chain_id):
    _, source = make_journal(
        0,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    with pytest.raises(ValueError, match="chain_id"):
        DurableChainReplicator(
            chain_id,
            source,
            target,
        )


def test_require_in_sync_accepts_synced_replica():
    _, source = make_journal(
        2,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    replicator = journal_replicator(
        source,
        target,
    )
    replicator.sync()
    report = replicator.require_in_sync()
    assert report.in_sync


def test_require_in_sync_rejects_lag():
    _, source = make_journal(
        2,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    with pytest.raises(
        DurableReplicationError,
        match="not in sync",
    ):
        journal_replicator(
            source,
            target,
        ).require_in_sync()


def test_batch_serialization_and_digest():
    _, source = make_journal(
        2,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    batch = journal_replicator(
        source,
        target,
    ).sync_once()
    data = batch.to_dict()
    assert data["transferred_items"] == 2
    assert data["completed"] is True
    assert data["digest"] == batch.digest
    assert len(batch.digest) == 64


def test_run_serialization_and_digest():
    _, source = make_journal(
        3,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    run = journal_replicator(
        source,
        target,
        batch=2,
    ).sync()
    data = run.to_dict()
    assert data["completed"] is True
    assert data["transferred_items"] == 3
    assert data["digest"] == run.digest


def test_report_serialization_and_digest():
    _, source = make_journal(
        1,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    report = journal_replicator(
        source,
        target,
    ).inspect()
    data = report.to_dict()
    assert data["state"] == "lagging"
    assert data["syncable"] is True
    assert data["digest"] == report.digest


def test_evidence_replica_manager_inspects_both_chains():
    _, source_journal = make_journal(
        2,
        namespace="source-journal",
    )
    _, target_journal = make_journal(
        0,
        namespace="target-journal",
    )
    _, source_receipts = make_receipts(
        3,
        namespace="source-receipts",
    )
    _, target_receipts = make_receipts(
        0,
        namespace="target-receipts",
    )
    manager = DurableEvidenceReplicaManager(
        journal_replicator(
            source_journal,
            target_journal,
        ),
        receipt_replicator(
            source_receipts,
            target_receipts,
        ),
    )
    report = manager.inspect()
    assert not report.in_sync
    assert report.journal.lag_items == 2
    assert report.receipts.lag_items == 3
    assert report.max_lag_items == 3
    assert not report.promotion_ready


def test_evidence_replica_manager_syncs_both_chains():
    _, source_journal = make_journal(
        5,
        namespace="source-journal",
    )
    _, target_journal = make_journal(
        0,
        namespace="target-journal",
    )
    _, source_receipts = make_receipts(
        4,
        namespace="source-receipts",
    )
    _, target_receipts = make_receipts(
        0,
        namespace="target-receipts",
    )
    manager = DurableEvidenceReplicaManager(
        journal_replicator(
            source_journal,
            target_journal,
            batch=2,
        ),
        receipt_replicator(
            source_receipts,
            target_receipts,
            batch=2,
        ),
    )
    run = manager.sync()
    assert run.completed
    assert run.transferred_items == 9
    assert run.final.in_sync
    assert run.final.promotion_ready
    assert target_journal.snapshot() == source_journal.snapshot()
    assert target_receipts.snapshot() == source_receipts.snapshot()


def test_promotion_guard_requires_both_chains_in_sync():
    _, source_journal = make_journal(
        1,
        namespace="source-journal",
    )
    _, target_journal = make_journal(
        0,
        namespace="target-journal",
    )
    _, source_receipts = make_receipts(
        1,
        namespace="source-receipts",
    )
    _, target_receipts = make_receipts(
        0,
        namespace="target-receipts",
    )
    manager = DurableEvidenceReplicaManager(
        journal_replicator(
            source_journal,
            target_journal,
        ),
        receipt_replicator(
            source_receipts,
            target_receipts,
        ),
    )
    with pytest.raises(
        DurableReplicationError,
        match="not promotion ready",
    ):
        manager.require_promotion_ready()
    manager.sync()
    assert manager.require_promotion_ready().promotion_ready


def test_manager_rejects_wrong_replicator_types():
    _, source = make_journal(
        0,
        namespace="source",
    )
    _, target = make_journal(
        0,
        namespace="target",
    )
    good = journal_replicator(
        source,
        target,
    )
    with pytest.raises(TypeError, match="journal"):
        DurableEvidenceReplicaManager(
            object(),
            good,
        )
    with pytest.raises(TypeError, match="receipts"):
        DurableEvidenceReplicaManager(
            good,
            object(),
        )


def test_manager_report_digest_is_stable():
    _, source_journal = make_journal(
        0,
        namespace="source-journal",
    )
    _, target_journal = make_journal(
        0,
        namespace="target-journal",
    )
    _, source_receipts = make_receipts(
        0,
        namespace="source-receipts",
    )
    _, target_receipts = make_receipts(
        0,
        namespace="target-receipts",
    )
    manager = DurableEvidenceReplicaManager(
        journal_replicator(
            source_journal,
            target_journal,
        ),
        receipt_replicator(
            source_receipts,
            target_receipts,
        ),
    )
    first = manager.inspect()
    second = manager.inspect()
    assert first == second
    assert first.digest == second.digest


def test_manager_run_digest_is_stable_after_completion():
    _, source_journal = make_journal(
        2,
        namespace="source-journal",
    )
    _, target_journal = make_journal(
        0,
        namespace="target-journal",
    )
    _, source_receipts = make_receipts(
        2,
        namespace="source-receipts",
    )
    _, target_receipts = make_receipts(
        0,
        namespace="target-receipts",
    )
    manager = DurableEvidenceReplicaManager(
        journal_replicator(
            source_journal,
            target_journal,
        ),
        receipt_replicator(
            source_receipts,
            target_receipts,
        ),
    )
    run = manager.sync()
    assert len(run.digest) == 64
    data = run.to_dict()
    assert data["digest"] == run.digest
    assert data["final"]["promotion_ready"] is True


def test_report_constructor_validates_roots():
    with pytest.raises(ValueError, match="source_root"):
        DurableChainReplicationReport(
            "chain",
            DurableReplicaState.IN_SYNC,
            0,
            "bad",
            0,
            fp("a"),
            0,
            True,
            True,
            None,
            "",
            "",
            fp("p"),
        )


def test_batch_constructor_validates_sequence_count():
    report = DurableChainReplicationReport(
        "chain",
        DurableReplicaState.LAGGING,
        2,
        fp("a"),
        0,
        fp("b"),
        2,
        True,
        True,
        1,
        fp("c"),
        "",
        fp("p"),
    )
    with pytest.raises(ValueError, match="sequence range"):
        DurableReplicationBatch(
            "chain",
            report,
            report,
            2,
            1,
            1,
            fp("b"),
            fp("c"),
        )


def test_run_constructor_validates_batch_limit():
    report = DurableChainReplicationReport(
        "chain",
        DurableReplicaState.IN_SYNC,
        0,
        fp("a"),
        0,
        fp("a"),
        0,
        True,
        True,
        None,
        "",
        "",
        fp("p"),
    )
    batch = DurableReplicationBatch(
        "chain",
        report,
        report,
        0,
        None,
        None,
        fp("a"),
        fp("a"),
    )
    with pytest.raises(ValueError, match="exceeds"):
        DurableReplicationRun(
            "chain",
            report,
            report,
            (batch, batch),
            1,
        )


def test_evidence_report_promotion_requires_valid_both():
    good = DurableChainReplicationReport(
        "journal",
        DurableReplicaState.IN_SYNC,
        1,
        fp("a"),
        1,
        fp("a"),
        0,
        True,
        True,
        None,
        "",
        "",
        fp("p"),
    )
    bad = DurableChainReplicationReport(
        "receipts",
        DurableReplicaState.IN_SYNC,
        1,
        fp("b"),
        1,
        fp("b"),
        0,
        False,
        True,
        None,
        "",
        "",
        fp("p"),
    )
    report = DurableEvidenceReplicationReport(
        good,
        bad,
        fp("p"),
    )
    assert report.in_sync
    assert not report.promotion_ready
