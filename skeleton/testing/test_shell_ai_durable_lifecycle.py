"""Durable evidence lifecycle coordinator tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import DurableArchiveManifestBuilder
from skeleton.shells.ai.durable_archive_store import DurableArchiveRepository
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionPolicy,
)
from skeleton.shells.ai.durable_lifecycle import (
    DurableEvidenceLifecycleCoordinator,
    DurableLifecycleAction,
    DurableLifecycleError,
    DurableLifecyclePolicy,
    DurableLifecycleReport,
    DurableLifecycleState,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def build_components(
    *,
    max_events=10,
    minimum_live_tail=2,
    minimum_archive_batch=2,
    target_utilization=0.5,
    lifecycle_policy=None,
    compaction_policy=None,
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=max_events,
        clock=lambda: 10.0,
    )
    checkpoint_signer = ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )
    archive_signer = ArtifactSigner(
        "archive",
        b"a" * 32,
        clock=lambda: 200.0,
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer,
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=minimum_live_tail,
            minimum_archive_batch=minimum_archive_batch,
            target_utilization=target_utilization,
            warning_utilization=max(
                target_utilization,
                0.8,
            ),
            critical_utilization=0.95,
            max_protected_roots=32,
        ),
    )
    archive_builder = DurableArchiveManifestBuilder(
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
    compaction = DurableCompactionPlanner(
        archives,
        compaction_policy
        or DurableCompactionPolicy(
            minimum_live_tail=minimum_live_tail,
            maximum_candidate_nodes=max_events,
            max_protected_roots=32,
        ),
    )
    coordinator = DurableEvidenceLifecycleCoordinator(
        checkpoints,
        retention,
        archive_builder,
        archives,
        compaction,
        lifecycle_policy,
    )
    return (
        backend,
        journal,
        checkpoints,
        retention,
        archive_builder,
        archives,
        compaction,
        coordinator,
    )


def append_events(journal, count, *, start=0):
    result = []
    for index in range(start, start + count):
        result.append(
            journal.append(
                "lifecycle.event",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
            )
        )
    return tuple(result)


def test_healthy_chain_is_noop():
    fixture = build_components(
        max_events=100,
        target_utilization=0.8,
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 2)
    report = coordinator.inspect(
        "journal",
        journal,
    )
    assert report.state is DurableLifecycleState.HEALTHY
    assert report.action is DurableLifecycleAction.NONE
    assert report.ok
    assert report.checkpoint is None
    assert report.archive is None
    assert report.compaction is None
    assert not report.destructive_action_authorized


def test_pressure_without_checkpoint_requires_checkpoint():
    fixture = build_components()
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 8)
    report = coordinator.inspect(
        "journal",
        journal,
    )
    assert (
        report.state
        is DurableLifecycleState.CHECKPOINT_REQUIRED
    )
    assert report.action is DurableLifecycleAction.NONE
    assert not report.ok
    assert any(
        "checkpoint" in reason
        for reason in report.reasons
    )


def test_prepare_primes_checkpoint_under_pressure():
    fixture = build_components()
    journal = fixture[1]
    checkpoints = fixture[2]
    coordinator = fixture[7]
    append_events(journal, 8)

    report = coordinator.prepare(
        "journal",
        journal,
    )
    assert (
        report.state
        is DurableLifecycleState.CHECKPOINT_PRIMED
    )
    assert (
        report.action
        is DurableLifecycleAction.CHECKPOINT_PUBLISHED
    )
    assert report.ok
    assert report.checkpoint is not None
    assert report.checkpoint.checkpoint.sequence == 8
    assert (
        checkpoints.latest("journal")
        == report.checkpoint
    )
    assert not report.destructive_action_authorized


def test_checkpoint_prime_is_future_eligibility_not_immediate_archive():
    fixture = build_components()
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 8)
    first = coordinator.prepare(
        "journal",
        journal,
    )
    assert (
        first.state
        is DurableLifecycleState.CHECKPOINT_PRIMED
    )
    second = coordinator.inspect(
        "journal",
        journal,
    )
    assert (
        second.state
        in {
            DurableLifecycleState.CHECKPOINT_REQUIRED,
            DurableLifecycleState.BLOCKED,
        }
    )
    assert not second.retention.archive_recommended


def test_tail_growth_turns_primed_checkpoint_into_archive_candidate():
    fixture = build_components()
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 6)
    primed = coordinator.prepare(
        "journal",
        journal,
    )
    assert primed.checkpoint is not None
    assert primed.checkpoint.checkpoint.sequence == 6

    append_events(
        journal,
        2,
        start=6,
    )
    report = coordinator.inspect(
        "journal",
        journal,
    )
    assert (
        report.state
        is DurableLifecycleState.ARCHIVE_REQUIRED
    )
    assert report.retention.archive_recommended
    assert report.retention.archive_through_sequence == 6
    assert report.checkpoint is not None


def test_prepare_persists_archive_and_reaches_compaction_ready():
    fixture = build_components()
    journal = fixture[1]
    archives = fixture[5]
    coordinator = fixture[7]

    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    report = coordinator.prepare(
        "journal",
        journal,
    )
    assert (
        report.state
        is DurableLifecycleState.COMPACTION_READY
    )
    assert (
        report.action
        is DurableLifecycleAction.ARCHIVE_PERSISTED
    )
    assert report.ok
    assert report.archive is not None
    assert report.archive_store is not None
    assert report.archive_store.fresh_write
    assert report.compaction is not None
    assert report.compaction.ready
    assert not report.destructive_action_authorized
    assert archives.verify_root(
        "journal",
        report.retention.archive_through_root,
    )


def test_prepare_is_idempotent_after_archive_exists():
    fixture = build_components()
    journal = fixture[1]
    coordinator = fixture[7]

    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    first = coordinator.prepare(
        "journal",
        journal,
    )
    second = coordinator.prepare(
        "journal",
        journal,
    )
    assert first.state is DurableLifecycleState.COMPACTION_READY
    assert second.state is DurableLifecycleState.COMPACTION_READY
    assert second.action is DurableLifecycleAction.NONE
    assert second.archive is not None
    assert second.archive.manifest.archive_id == (
        first.archive.manifest.archive_id
    )


def test_inspect_existing_archive_does_not_claim_mutation():
    fixture = build_components()
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    coordinator.prepare(
        "journal",
        journal,
    )
    inspected = coordinator.inspect(
        "journal",
        journal,
    )
    assert inspected.state is DurableLifecycleState.COMPACTION_READY
    assert inspected.action is DurableLifecycleAction.NONE


def test_policy_can_disable_checkpoint_priming():
    fixture = build_components(
        lifecycle_policy=DurableLifecyclePolicy(
            prime_checkpoint_on_pressure=False,
        )
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 8)
    report = coordinator.prepare(
        "journal",
        journal,
    )
    assert (
        report.state
        is DurableLifecycleState.CHECKPOINT_REQUIRED
    )
    assert report.action is DurableLifecycleAction.NONE
    assert report.checkpoint is None


def test_policy_can_disable_archive_persistence():
    fixture = build_components(
        lifecycle_policy=DurableLifecyclePolicy(
            persist_archive_when_recommended=False,
        )
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    report = coordinator.prepare(
        "journal",
        journal,
    )
    assert (
        report.state
        is DurableLifecycleState.ARCHIVE_REQUIRED
    )
    assert report.archive is None


def test_archive_stored_but_not_ready_is_blocked_when_policy_requires_readiness():
    fixture = build_components(
        compaction_policy=DurableCompactionPolicy(
            minimum_live_tail=3,
            maximum_candidate_nodes=10,
        )
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    report = coordinator.prepare(
        "journal",
        journal,
    )
    assert report.state is DurableLifecycleState.BLOCKED
    assert report.action is DurableLifecycleAction.ARCHIVE_PERSISTED
    assert not report.ok
    assert report.archive is not None
    assert report.compaction is not None
    assert not report.compaction.ready


def test_archive_stored_can_be_operational_when_readiness_not_required():
    fixture = build_components(
        lifecycle_policy=DurableLifecyclePolicy(
            require_compaction_ready_after_archive=False,
        ),
        compaction_policy=DurableCompactionPolicy(
            minimum_live_tail=3,
            maximum_candidate_nodes=10,
        ),
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    report = coordinator.prepare(
        "journal",
        journal,
    )
    assert (
        report.state
        is DurableLifecycleState.ARCHIVE_STORED
    )
    assert report.ok
    assert report.archive_persisted
    assert not report.destructive_action_authorized


def test_require_operational_accepts_healthy_chain():
    fixture = build_components(
        max_events=100,
        target_utilization=0.8,
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 2)
    report = coordinator.require_operational(
        "journal",
        journal,
    )
    assert report.ok


def test_require_operational_rejects_archive_required():
    fixture = build_components()
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    with pytest.raises(
        DurableLifecycleError,
    ):
        coordinator.require_operational(
            "journal",
            journal,
        )


def test_archive_tamper_blocks_lifecycle():
    fixture = build_components()
    backend = fixture[0]
    journal = fixture[1]
    archives = fixture[5]
    coordinator = fixture[7]
    append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    ready = coordinator.prepare(
        "journal",
        journal,
    )
    assert ready.archive is not None

    root = ready.retention.archive_through_root
    key = archives._node_key(
        "journal",
        root,
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

    report = coordinator.inspect(
        "journal",
        journal,
    )
    assert report.state is DurableLifecycleState.BLOCKED
    assert not report.ok


def test_protected_root_is_carried_into_compaction_readiness():
    fixture = build_components()
    journal = fixture[1]
    coordinator = fixture[7]
    first = append_events(journal, 6)
    coordinator.prepare(
        "journal",
        journal,
    )
    append_events(
        journal,
        2,
        start=6,
    )
    protected = first[1].event_hash
    report = coordinator.prepare(
        "journal",
        journal,
        protected_roots=(protected,),
    )
    assert report.compaction is not None
    assert report.compaction.ready
    assert len(
        report.compaction.protected_roots
    ) == 1
    assert (
        report.compaction.protected_roots[0]
        .root_hash
        == protected
    )


def test_lifecycle_protected_root_bound():
    fixture = build_components(
        lifecycle_policy=DurableLifecyclePolicy(
            max_protected_roots=2,
        )
    )
    journal = fixture[1]
    coordinator = fixture[7]
    events = append_events(
        journal,
        3,
    )
    with pytest.raises(
        ValueError,
        match="protected root bound",
    ):
        coordinator.inspect(
            "journal",
            journal,
            protected_roots=tuple(
                item.event_hash
                for item in events
            ),
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


def test_receipt_chain_lifecycle_reaches_compaction_ready():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=10,
    )
    checkpoint_signer = ArtifactSigner(
        "checkpoint",
        b"c" * 32,
    )
    archive_signer = ArtifactSigner(
        "archive",
        b"a" * 32,
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer,
        namespace="checkpoints",
    )
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=0.5,
            warning_utilization=0.8,
            critical_utilization=0.95,
        ),
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
    compaction = DurableCompactionPlanner(
        archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=10,
        ),
    )
    coordinator = DurableEvidenceLifecycleCoordinator(
        checkpoints,
        retention,
        builder,
        archives,
        compaction,
    )
    tuple(
        receipts.append(receipt(index))
        for index in range(6)
    )
    coordinator.prepare(
        "receipts",
        receipts,
    )
    tuple(
        receipts.append(receipt(index))
        for index in range(6, 8)
    )
    report = coordinator.prepare(
        "receipts",
        receipts,
    )
    assert (
        report.state
        is DurableLifecycleState.COMPACTION_READY
    )
    assert report.compaction.ready
    assert not report.destructive_action_authorized


@pytest.mark.parametrize(
    "field,value",
    [
        ("prime_checkpoint_on_pressure", "yes"),
        ("persist_archive_when_recommended", 1),
        ("require_compaction_ready_after_archive", None),
    ],
)
def test_lifecycle_policy_boolean_validation(field, value):
    values = dict(
        prime_checkpoint_on_pressure=True,
        persist_archive_when_recommended=True,
        require_compaction_ready_after_archive=True,
    )
    values[field] = value
    with pytest.raises(ValueError, match="bool"):
        DurableLifecyclePolicy(
            **values
        )


@pytest.mark.parametrize(
    "value",
    [0, -1, True, 1.5],
)
def test_lifecycle_policy_root_bound_validation(value):
    with pytest.raises(
        ValueError,
        match="max_protected_roots",
    ):
        DurableLifecyclePolicy(
            max_protected_roots=value,
        )


def test_lifecycle_policy_digest_is_stable():
    first = DurableLifecyclePolicy()
    second = DurableLifecyclePolicy()
    assert first.digest == second.digest


def test_lifecycle_report_serialization():
    fixture = build_components(
        max_events=100,
        target_utilization=0.8,
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 2)
    report = coordinator.inspect(
        "journal",
        journal,
    )
    data = report.to_dict()
    assert data["state"] == "healthy"
    assert data["action"] == "none"
    assert data["ok"] is True
    assert (
        data["destructive_action_authorized"]
        is False
    )
    assert data["digest"] == report.digest


def test_lifecycle_report_digest_is_stable():
    fixture = build_components(
        max_events=100,
        target_utilization=0.8,
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 2)
    first = coordinator.inspect(
        "journal",
        journal,
    )
    second = coordinator.inspect(
        "journal",
        journal,
    )
    assert first.digest == second.digest
    assert first == second


def test_lifecycle_report_rejects_chain_mismatch():
    fixture = build_components(
        max_events=100,
        target_utilization=0.8,
    )
    journal = fixture[1]
    coordinator = fixture[7]
    append_events(journal, 2)
    report = coordinator.inspect(
        "journal",
        journal,
    )
    with pytest.raises(
        ValueError,
        match="chain_id differs",
    ):
        replace(
            report,
            chain_id="other",
        )


@pytest.mark.parametrize(
    "state",
    [
        "healthy",
        "checkpoint_required",
        "checkpoint_primed",
        "archive_required",
        "archive_stored",
        "compaction_ready",
        "blocked",
    ],
)
def test_lifecycle_state_wire_values(state):
    assert (
        DurableLifecycleState(state).value
        == state
    )


@pytest.mark.parametrize(
    "action",
    [
        "none",
        "checkpoint_published",
        "archive_persisted",
        "archive_reused",
    ],
)
def test_lifecycle_action_wire_values(action):
    assert (
        DurableLifecycleAction(action).value
        == action
    )


def test_lifecycle_constructor_type_validation():
    fixture = build_components()
    args = list(
        (
            fixture[2],
            fixture[3],
            fixture[4],
            fixture[5],
            fixture[6],
        )
    )
    labels = (
        "checkpoints",
        "retention",
        "archive_builder",
        "archives",
        "compaction",
    )
    for index, label in enumerate(labels):
        broken = list(args)
        broken[index] = object()
        with pytest.raises(
            TypeError,
            match=label,
        ):
            DurableEvidenceLifecycleCoordinator(
                *broken
            )


def test_lifecycle_error_is_runtime_error():
    assert issubclass(
        DurableLifecycleError,
        RuntimeError,
    )
