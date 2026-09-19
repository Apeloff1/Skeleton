"""Archive-backed durable compaction readiness tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import DurableArchiveManifestBuilder
from skeleton.shells.ai.durable_archive_store import (
    DurableArchiveRepository,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionError,
    DurableCompactionPlanner,
    DurableCompactionPolicy,
    DurableCompactionReadiness,
    DurableCompactionRootCoverage,
    DurableCompactionState,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
    ProtectedHistoricalRoot,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(
        value.encode()
    ).hexdigest()


def signers():
    return (
        ArtifactSigner(
            "checkpoint",
            b"c" * 32,
            clock=lambda: 100.0,
        ),
        ArtifactSigner(
            "archive",
            b"a" * 32,
            clock=lambda: 200.0,
        ),
    )


def append_events(journal, count, *, start=0):
    result = []
    for index in range(start, start + count):
        result.append(
            journal.append(
                "compaction.event",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
            )
        )
    return tuple(result)


def journal_ready_fixture(
    *,
    protected_roots=(),
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=10,
        clock=lambda: 10.0,
    )
    checkpoint_signer, archive_signer = signers()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer,
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer,
        clock=lambda: 200.0,
    )
    archives = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer,
        namespace="archives",
        clock=lambda: 300.0,
    )

    first = append_events(journal, 6)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    archives.put(
        archive,
        checkpoint,
        journal,
    )
    later = append_events(
        journal,
        2,
        start=6,
    )

    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=0.50,
            warning_utilization=0.70,
            critical_utilization=0.95,
            max_protected_roots=32,
        ),
    ).plan(
        "journal",
        journal,
        protected_roots=tuple(
            protected_roots
        ),
    )
    planner = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=10,
            max_protected_roots=32,
        ),
    )
    return (
        backend,
        journal,
        checkpoints,
        archives,
        first,
        later,
        retention,
        planner,
        archive,
    )


def test_ready_compaction_after_verified_archive():
    (
        _,
        journal,
        _,
        _,
        first,
        later,
        retention,
        planner,
        archive,
    ) = journal_ready_fixture()
    report = planner.require_ready(
        retention,
        journal,
    )
    assert report.ready
    assert report.state is DurableCompactionState.READY
    assert report.current_sequence == 8
    assert report.cutoff_sequence == 6
    assert report.cutoff_root == first[-1].event_hash
    assert report.live_tail == 2
    assert report.candidate_nodes == 6
    assert report.archive_verified
    assert report.cutoff_archived
    assert report.archive_id == archive.manifest.archive_id
    assert report.current_root == later[-1].event_hash
    assert not report.destructive_action_authorized


def test_ready_report_never_authorizes_deletion():
    fixture = journal_ready_fixture()
    journal = fixture[1]
    retention = fixture[6]
    planner = fixture[7]
    report = planner.require_ready(
        retention,
        journal,
    )
    assert report.ready is True
    assert (
        report.destructive_action_authorized
        is False
    )
    assert any(
        "does not authorize destructive deletion"
        in reason
        for reason in report.reasons
    )


def test_missing_archive_is_not_ready():
    (
        backend,
        journal,
        checkpoints,
        _,
        first,
        _,
        retention,
        _,
        _,
    ) = journal_ready_fixture()
    _, archive_signer = signers()
    empty_archives = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer,
        namespace="empty-archives",
    )
    planner = DurableCompactionPlanner(
        empty_archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=10,
        ),
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.ARCHIVE_MISSING
    )
    assert not report.ready
    assert report.cutoff_root == first[-1].event_hash
    with pytest.raises(
        DurableCompactionError,
        match="not present",
    ):
        planner.require_ready(
            retention,
            journal,
        )


def test_stale_retention_plan_is_rejected_after_chain_advances():
    (
        _,
        journal,
        _,
        _,
        _,
        _,
        retention,
        planner,
        _,
    ) = journal_ready_fixture()
    append_events(
        journal,
        1,
        start=8,
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.STALE_RETENTION_PLAN
    )
    assert any(
        "head differs" in reason
        for reason in report.reasons
    )


def test_policy_can_allow_head_drift_but_archive_cutoff_still_verified():
    (
        _,
        journal,
        _,
        archives,
        _,
        _,
        retention,
        _,
        _,
    ) = journal_ready_fixture()
    append_events(
        journal,
        1,
        start=8,
    )
    planner = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=10,
            require_current_head_match=False,
        ),
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert report.ready
    assert report.live_tail == 3


def test_minimum_live_tail_is_enforced():
    (
        _,
        journal,
        _,
        archives,
        _,
        _,
        retention,
        _,
        _,
    ) = journal_ready_fixture()
    planner = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=3,
            maximum_candidate_nodes=10,
        ),
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.LIVE_TAIL_TOO_SMALL
    )
    assert not report.ready


def test_candidate_bound_is_enforced():
    (
        _,
        journal,
        _,
        archives,
        _,
        _,
        retention,
        _,
        _,
    ) = journal_ready_fixture()
    planner = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=5,
        ),
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.STALE_RETENTION_PLAN
    )
    assert any(
        "exceeds compaction policy bound"
        in reason
        for reason in report.reasons
    )


def test_no_archive_candidate_is_explicit():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=100,
        clock=lambda: 1.0,
    )
    append_events(journal, 2)
    checkpoint_signer, archive_signer = signers()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer,
        namespace="checkpoints",
    )
    archives = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer,
        namespace="archives",
    )
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=1,
            minimum_archive_batch=1,
            target_utilization=0.90,
            warning_utilization=0.95,
            critical_utilization=1.0,
        ),
    ).plan(
        "journal",
        journal,
    )
    report = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=1,
        ),
    ).inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.NO_ARCHIVE_CANDIDATE
    )


class InvalidChainView:
    def __init__(self, delegate):
        self.delegate = delegate

    def head(self):
        return self.delegate.head()

    def verify(self):
        return False

    def verify_root(self, root_hash):
        return self.delegate.verify_root(root_hash)

    def root_is_ancestor(self, root_hash):
        return self.delegate.root_is_ancestor(root_hash)

    def snapshot_at(self, root_hash):
        return self.delegate.snapshot_at(root_hash)


def test_invalid_live_chain_is_not_ready():
    fixture = journal_ready_fixture()
    journal = fixture[1]
    retention = fixture[6]
    planner = fixture[7]
    report = planner.inspect(
        retention,
        InvalidChainView(journal),
    )
    assert (
        report.state
        is DurableCompactionState.CHAIN_INVALID
    )


def test_protected_evicted_root_requires_archive_coverage():
    fixture = journal_ready_fixture()
    (
        backend,
        journal,
        _,
        archives,
        first,
        _,
        _,
        planner,
        _,
    ) = fixture
    protected = first[1].event_hash
    # Build a retention plan carrying the protected root.
    retention = DurableRetentionPlanner(
        fixture[2],
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.95,
            max_protected_roots=32,
        ),
    ).plan(
        "journal",
        journal,
        protected_roots=(protected,),
    )
    report = planner.require_ready(
        retention,
        journal,
    )
    assert len(report.protected_roots) == 1
    coverage = report.protected_roots[0]
    assert coverage.would_be_evicted
    assert coverage.archived
    assert coverage.live
    assert coverage.covered

    key = archives._root_key(
        "journal",
        protected,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    backend.delete(
        archives.namespace,
        key,
        expected_revision=record.revision,
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.PROTECTED_ROOT_GAP
    )
    assert not report.protected_roots[0].covered


def test_protected_root_above_cutoff_can_remain_live_only():
    fixture = journal_ready_fixture()
    (
        _,
        journal,
        checkpoints,
        archives,
        _,
        later,
        _,
        _,
        _,
    ) = fixture
    protected = later[0].event_hash
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.95,
            max_protected_roots=32,
        ),
    ).plan(
        "journal",
        journal,
        protected_roots=(protected,),
    )
    planner = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=10,
        ),
    )
    report = planner.require_ready(
        retention,
        journal,
    )
    coverage = report.protected_roots[0]
    assert not coverage.would_be_evicted
    assert not coverage.archived
    assert coverage.live
    assert coverage.covered


def test_policy_can_allow_evicted_protected_root_live_coverage():
    fixture = journal_ready_fixture()
    (
        backend,
        journal,
        checkpoints,
        archives,
        first,
        _,
        _,
        _,
        _,
    ) = fixture
    protected = first[0].event_hash
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.95,
        ),
    ).plan(
        "journal",
        journal,
        protected_roots=(protected,),
    )
    key = archives._root_key(
        "journal",
        protected,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    backend.delete(
        archives.namespace,
        key,
        expected_revision=record.revision,
    )
    planner = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=10,
            require_archive_for_evicted_protected_roots=False,
        ),
    )
    report = planner.require_ready(
        retention,
        journal,
    )
    assert report.protected_roots[0].live
    assert not report.protected_roots[0].archived
    assert report.protected_roots[0].covered


def test_tampered_archive_node_makes_cutoff_invalid():
    (
        backend,
        journal,
        _,
        archives,
        first,
        _,
        retention,
        planner,
        _,
    ) = journal_ready_fixture()
    node_hash = first[-1].event_hash
    key = archives._node_key(
        "journal",
        node_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    payload["summary"] = "tampered"
    raw["payload"] = payload
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.ARCHIVE_INVALID
    )
    assert not report.archive_verified
    assert not report.cutoff_archived


def test_missing_archive_record_makes_cutoff_invalid():
    (
        backend,
        journal,
        _,
        archives,
        _,
        _,
        retention,
        planner,
        archive,
    ) = journal_ready_fixture()
    key = archives._archive_key(
        archive.manifest.archive_id
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    backend.delete(
        archives.namespace,
        key,
        expected_revision=record.revision,
    )
    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.ARCHIVE_INVALID
    )


def test_require_ready_raises_with_reason():
    fixture = journal_ready_fixture()
    journal = fixture[1]
    retention = fixture[6]
    archives = fixture[3]
    planner = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=99,
        ),
    )
    with pytest.raises(
        DurableCompactionError,
        match="minimum live tail",
    ):
        planner.require_ready(
            retention,
            journal,
        )


def receipt(index):
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
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


def test_receipt_chain_compaction_readiness():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=10,
    )
    first = tuple(
        receipts.append(receipt(index))
        for index in range(6)
    )
    checkpoint_signer, archive_signer = signers()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer,
        namespace="checkpoints",
    )
    checkpoint = checkpoints.publish(
        "receipts",
        receipts,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer,
    )
    archives = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer,
        namespace="archives",
    )
    archive = builder.build(
        checkpoint,
        receipts,
    )
    archives.put(
        archive,
        checkpoint,
        receipts,
    )
    tuple(
        receipts.append(receipt(index))
        for index in range(6, 8)
    )
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.95,
        ),
    ).plan(
        "receipts",
        receipts,
    )
    report = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=10,
        ),
    ).require_ready(
        retention,
        receipts,
    )
    assert report.ready
    assert report.cutoff_root == first[-1].receipt_hash
    assert report.candidate_nodes == 6
    assert not report.destructive_action_authorized


@pytest.mark.parametrize(
    "field,value",
    [
        ("minimum_live_tail", -1),
        ("maximum_candidate_nodes", 0),
        ("max_protected_roots", 0),
        ("maximum_candidate_nodes", True),
    ],
)
def test_compaction_policy_validation(field, value):
    values = dict(
        minimum_live_tail=1,
        maximum_candidate_nodes=10,
        max_protected_roots=10,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableCompactionPolicy(
            **values
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("require_current_head_match", "yes"),
        (
            "require_archive_for_evicted_protected_roots",
            1,
        ),
    ],
)
def test_compaction_policy_boolean_validation(field, value):
    values = dict(
        require_current_head_match=True,
        require_archive_for_evicted_protected_roots=True,
    )
    values[field] = value
    with pytest.raises(ValueError, match="bool"):
        DurableCompactionPolicy(
            **values
        )


def test_compaction_policy_digest_is_stable():
    first = DurableCompactionPolicy(
        minimum_live_tail=2,
        maximum_candidate_nodes=10,
    )
    second = DurableCompactionPolicy(
        minimum_live_tail=2,
        maximum_candidate_nodes=10,
    )
    assert first.digest == second.digest


def test_compaction_root_coverage_validation():
    with pytest.raises(ValueError):
        DurableCompactionRootCoverage(
            "bad",
            1,
            True,
            True,
            True,
            True,
        )
    with pytest.raises(ValueError):
        DurableCompactionRootCoverage(
            fp("root"),
            -1,
            True,
            True,
            True,
            True,
        )
    with pytest.raises(ValueError):
        DurableCompactionRootCoverage(
            fp("root"),
            1,
            True,
            False,
            False,
            True,
        )


def test_compaction_readiness_serialization():
    fixture = journal_ready_fixture()
    report = fixture[7].require_ready(
        fixture[6],
        fixture[1],
    )
    data = report.to_dict()
    assert data["state"] == "ready"
    assert data["ready"] is True
    assert (
        data["destructive_action_authorized"]
        is False
    )
    assert data["digest"] == report.digest
    assert data["candidate_nodes"] == 6


def test_compaction_readiness_digest_is_stable():
    fixture = journal_ready_fixture()
    planner = fixture[7]
    first = planner.require_ready(
        fixture[6],
        fixture[1],
    )
    second = planner.require_ready(
        fixture[6],
        fixture[1],
    )
    assert first.digest == second.digest
    assert first == second


def test_compaction_readiness_validates_live_tail_consistency():
    fixture = journal_ready_fixture()
    report = fixture[7].require_ready(
        fixture[6],
        fixture[1],
    )
    with pytest.raises(ValueError, match="live_tail"):
        replace(
            report,
            live_tail=report.live_tail + 1,
        )


def test_compaction_readiness_validates_candidate_count_consistency():
    fixture = journal_ready_fixture()
    report = fixture[7].require_ready(
        fixture[6],
        fixture[1],
    )
    with pytest.raises(ValueError, match="candidate"):
        replace(
            report,
            candidate_nodes=report.candidate_nodes + 1,
        )


def test_compaction_planner_constructor_type():
    with pytest.raises(TypeError, match="archives"):
        DurableCompactionPlanner(
            object()
        )


def test_compaction_inspect_type_validation():
    fixture = journal_ready_fixture()
    planner = fixture[7]
    with pytest.raises(TypeError, match="retention"):
        planner.inspect(
            object(),
            fixture[1],
        )
    with pytest.raises(TypeError, match="chain"):
        planner.inspect(
            fixture[6],
            object(),
        )


def test_protected_root_bound_is_enforced():
    fixture = journal_ready_fixture()
    journal = fixture[1]
    events = journal.snapshot()
    protected = tuple(
        ProtectedHistoricalRoot(
            events[index].event_hash,
            events[index].sequence,
        )
        for index in range(3)
    )
    retention = replace(
        fixture[6],
        protected_roots=protected,
    )
    planner = DurableCompactionPlanner(
        fixture[3],
        DurableCompactionPolicy(
            max_protected_roots=2,
        ),
    )
    with pytest.raises(
        ValueError,
        match="protected root bound",
    ):
        planner.inspect(
            retention,
            journal,
        )


def test_compaction_state_wire_values():
    assert {
        item.value
        for item in DurableCompactionState
    } == {
        "ready",
        "no_archive_candidate",
        "archive_missing",
        "archive_invalid",
        "stale_retention_plan",
        "live_tail_too_small",
        "protected_root_gap",
        "chain_invalid",
    }


def test_compaction_error_is_runtime_error():
    assert issubclass(
        DurableCompactionError,
        RuntimeError,
    )

def test_compaction_readiness_falls_back_to_secondary_archive_replica():
    (
        backend,
        journal,
        checkpoints,
        archives,
        _,
        _,
        retention,
        planner,
        first_archive,
    ) = journal_ready_fixture()

    # Archive the later current head as a second replica for every earlier root.
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archives.archive_signer,
    )
    second_checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    second_archive = builder.build(
        second_checkpoint,
        journal,
    )
    archives.put(
        second_archive,
        second_checkpoint,
        journal,
    )
    cutoff = retention.archive_through_root
    index = archives.root_index(
        "journal",
        cutoff,
    )
    assert len(index.replicas) == 2

    key = archives._archive_key(
        first_archive.manifest.archive_id
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    backend.delete(
        archives.namespace,
        key,
        expected_revision=record.revision,
    )

    report = planner.require_ready(
        retention,
        journal,
    )
    assert report.ready
    assert (
        report.archive_id
        == second_archive.manifest.archive_id
    )
    assert report.cutoff_archived


def test_compaction_readiness_fails_when_all_archive_replicas_are_missing():
    (
        backend,
        journal,
        checkpoints,
        archives,
        _,
        _,
        retention,
        planner,
        first_archive,
    ) = journal_ready_fixture()
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archives.archive_signer,
    )
    second_checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    second_archive = builder.build(
        second_checkpoint,
        journal,
    )
    archives.put(
        second_archive,
        second_checkpoint,
        journal,
    )
    for archive_id in (
        first_archive.manifest.archive_id,
        second_archive.manifest.archive_id,
    ):
        key = archives._archive_key(
            archive_id
        )
        record = backend.get(
            archives.namespace,
            key,
        )
        backend.delete(
            archives.namespace,
            key,
            expected_revision=record.revision,
        )

    report = planner.inspect(
        retention,
        journal,
    )
    assert (
        report.state
        is DurableCompactionState.ARCHIVE_INVALID
    )
    assert not report.ready

