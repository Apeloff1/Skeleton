"""Unified durable evidence readiness and reconciliation tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_operations import (
    DurableEvidenceOperationsInspector,
    DurableOperationsPolicy,
)
from skeleton.shells.ai.durable_readiness import (
    DurableEvidenceReadinessError,
    DurableEvidenceReadinessFinding,
    DurableEvidenceReadinessGuard,
    DurableEvidenceReadinessPolicy,
    DurableEvidenceReadinessReport,
    DurableEvidenceReadinessSeverity,
    DurableEvidenceReadinessState,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.durable_sequence_index import (
    DurableSequenceIndexOperator,
    DurableSequenceIndexPolicy,
)
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorStore,
    DurableVerificationPolicy,
)
from skeleton.shells.ai.durable_verification_operator import (
    DurableVerificationOperator,
    DurableVerificationOperatorPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def make_receipt(index: int) -> ExecutionReceipt:
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


def append_event(
    journal: DistributedAIDecisionJournal,
    index: int,
) -> None:
    journal.append(
        "readiness.event",
        session_id=f"session-{index}",
        intent_id=f"intent-{index}",
        proposal_id=f"proposal-{index}",
        summary=f"event {index}",
    )


class Environment:
    def __init__(
        self,
        *,
        journal_capacity=100,
        receipt_capacity=100,
        readiness_policy=None,
        sequence_policy=None,
        operations_policy=None,
        verification_policy=None,
    ):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            max_events=journal_capacity,
            clock=lambda: 10.0,
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
            max_receipts=receipt_capacity,
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            ArtifactSigner(
                "checkpoint",
                b"c" * 32,
                clock=lambda: 100.0,
            ),
            namespace="checkpoints",
            clock=lambda: 100.0,
        )
        self.retention = DurableRetentionPlanner(
            self.checkpoints,
            DurableRetentionPolicy(
                minimum_live_tail=1,
                minimum_archive_batch=1,
                target_utilization=0.60,
                warning_utilization=0.80,
                critical_utilization=0.95,
            ),
        )
        self.operations = DurableEvidenceOperationsInspector(
            self.checkpoints,
            self.retention,
            policy=(
                operations_policy
                or DurableOperationsPolicy()
            ),
        )
        self.cursor_store = DurableVerificationCursorStore(
            self.backend,
            ArtifactSigner(
                "cursor",
                b"v" * 32,
                clock=lambda: 100.0,
            ),
            namespace="cursors",
        )
        self.incremental = DurableIncrementalVerifier(
            self.cursor_store,
            verification_policy,
            clock=lambda: 100.0,
        )
        self.verification = DurableVerificationOperator(
            self.cursor_store,
            self.incremental,
            DurableVerificationOperatorPolicy(
                max_chains=8,
                max_lineage_items=512,
            ),
        )
        self.sequence_indexes = DurableSequenceIndexOperator(
            sequence_policy
            or DurableSequenceIndexPolicy(
                max_items_per_chain=1000,
                max_chains=8,
                sample_window_items=4,
            )
        )
        self.guard = DurableEvidenceReadinessGuard(
            self.operations,
            self.sequence_indexes,
            self.verification,
            readiness_policy,
        )

    @property
    def entries(self):
        return (
            ("journal", self.journal),
            ("receipts", self.receipts),
        )

    def append(self, count=1):
        start = self.journal.length() + 1
        for offset in range(count):
            index = start + offset
            append_event(self.journal, index)
            self.receipts.append(
                make_receipt(index)
            )

    def initialize_verification(self):
        return self.verification.force_full_refresh(
            self.entries
        )


def test_ready_after_full_cursor_initialization():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    report = env.guard.inspect(env.entries)
    assert report.ready
    assert report.state is DurableEvidenceReadinessState.READY
    assert report.errors == 0
    assert report.warnings == 0
    assert report.operations is not None
    assert report.operations.allowed
    assert report.sequence_indexes is not None
    assert report.sequence_indexes.ok
    assert report.verification is not None
    assert report.verification.ok
    assert report.mutations == ()


def test_require_ready_returns_ready_report():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    report = env.guard.require_ready(
        env.entries
    )
    assert report.ready
    assert not report.blocked


def test_uninitialized_verification_blocks_readiness():
    env = Environment()
    env.append(2)
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert report.state is DurableEvidenceReadinessState.BLOCKED
    assert any(
        item.code
        == "readiness.verification_not_current"
        for item in report.findings
    )


def test_reconcile_initializes_verification_cursors():
    env = Environment()
    env.append(2)
    report = env.guard.reconcile(env.entries)
    assert report.ready
    assert "verification_full_refresh" in report.mutations
    assert report.verification is not None
    assert report.verification.ok
    assert report.verification_refresh is not None
    assert report.verification_refresh.ok


def test_new_chain_items_make_cursor_behind():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    env.append(1)
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert not report.verification.ok
    assert any(
        item.code
        == "readiness.verification_not_current"
        for item in report.findings
    )


def test_reconcile_refreshes_behind_cursor():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    env.append(1)
    report = env.guard.reconcile(env.entries)
    assert report.ready
    assert report.mutations == (
        "verification_full_refresh",
    )


def test_missing_journal_sequence_index_blocks_readiness():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    key = env.journal._sequence_key(2)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert report.sequence_indexes.missing == 1
    assert any(
        item.code
        == "readiness.sequence_indexes_unhealthy"
        for item in report.findings
    )


def test_missing_receipt_sequence_index_blocks_readiness():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    key = env.receipts._sequence_key(2)
    record = env.backend.get(
        "receipts",
        key,
    )
    env.backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert report.sequence_indexes.missing == 1


def test_reconcile_repairs_missing_index():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    key = env.journal._sequence_key(2)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    report = env.guard.reconcile(env.entries)
    assert report.ready
    assert report.mutations == (
        "sequence_index_repair",
    )
    assert report.sequence_indexes.ok
    assert report.sequence_indexes.repaired == 1


def test_reconcile_can_repair_indexes_and_refresh_verification_together():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    key = env.journal._sequence_key(2)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    env.append(1)
    report = env.guard.reconcile(env.entries)
    assert report.ready
    assert report.mutations == (
        "sequence_index_repair",
        "verification_full_refresh",
    )


def test_corrupt_journal_index_blocks_and_is_not_repaired():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    events = env.journal.snapshot()
    key = env.journal._sequence_key(1)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            events[1].event_hash,
        ),
    )
    report = env.guard.reconcile(env.entries)
    assert report.blocked
    assert report.sequence_indexes.corrupt == 1
    assert "sequence_index_repair" not in report.mutations


def test_corrupt_receipt_index_blocks_and_is_not_repaired():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    items = env.receipts.snapshot()
    key = env.receipts._sequence_key(1)
    record = env.backend.get(
        "receipts",
        key,
    )
    env.backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            1,
            items[1].receipt_hash,
        ),
    )
    report = env.guard.reconcile(env.entries)
    assert report.blocked
    assert report.sequence_indexes.corrupt == 1


def test_sequence_repair_can_be_disabled():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            allow_sequence_index_repair=False,
        )
    )
    env.append(2)
    env.initialize_verification()
    key = env.journal._sequence_key(1)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableEvidenceReadinessError,
        match="repair required",
    ):
        env.guard.reconcile(env.entries)


def test_verification_refresh_can_be_disabled():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            allow_verification_refresh=False,
        )
    )
    env.append(2)
    with pytest.raises(
        DurableEvidenceReadinessError,
        match="refresh required",
    ):
        env.guard.reconcile(env.entries)


def test_operations_capacity_critical_blocks_readiness():
    env = Environment(
        journal_capacity=4,
        receipt_capacity=4,
    )
    env.append(4)
    env.initialize_verification()
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert report.operations is not None
    assert not report.operations.allowed
    assert any(
        item.code == "readiness.operations_denied"
        for item in report.findings
    )


def test_operations_requirement_can_be_advisory():
    env = Environment(
        journal_capacity=4,
        receipt_capacity=4,
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_operations_allowed=False,
        ),
    )
    env.append(4)
    env.initialize_verification()
    report = env.guard.inspect(env.entries)
    assert report.degraded
    assert report.state is DurableEvidenceReadinessState.DEGRADED
    assert report.errors == 0
    assert report.warnings >= 1


def test_sequence_requirement_can_be_advisory():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_sequence_indexes=False,
        )
    )
    env.append(2)
    env.initialize_verification()
    key = env.journal._sequence_key(1)
    record = env.backend.get("journal", key)
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    report = env.guard.inspect(env.entries)
    assert report.degraded
    assert report.errors == 0
    assert report.warnings == 1


def test_verification_requirement_can_be_advisory():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_verification_current=False,
        )
    )
    env.append(2)
    report = env.guard.inspect(env.entries)
    assert report.degraded
    assert report.errors == 0
    assert report.warnings == 1


def test_require_ready_rejects_degraded_state():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_verification_current=False,
        )
    )
    env.append(2)
    with pytest.raises(
        DurableEvidenceReadinessError,
        match="not current",
    ):
        env.guard.require_ready(env.entries)


def test_require_ready_can_reconcile():
    env = Environment()
    env.append(2)
    report = env.guard.require_ready(
        env.entries,
        reconcile=True,
    )
    assert report.ready
    assert report.repaired


def test_protected_roots_are_forwarded_to_operations():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    root = env.journal.root_hash()
    env.checkpoints.publish(
        "journal",
        env.journal,
    )
    report = env.guard.inspect(
        env.entries,
        protected_roots={
            "journal": (root,),
        },
    )
    assert report.ready
    journal_report = next(
        item
        for item in report.operations.chains
        if item.chain_id == "journal"
    )
    assert (
        journal_report.retention
        .protected_roots[0]
        .root_hash
        == root
    )


def test_chain_ids_are_sorted_in_report():
    env = Environment()
    env.append(1)
    env.initialize_verification()
    report = env.guard.inspect(
        tuple(reversed(env.entries))
    )
    assert report.chain_ids == (
        "journal",
        "receipts",
    )


def test_report_digest_is_deterministic():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    first = env.guard.inspect(env.entries)
    second = env.guard.inspect(env.entries)
    assert first.digest == second.digest
    assert first == second


def test_report_digest_changes_after_reconciliation():
    env = Environment()
    env.append(2)
    before = env.guard.inspect(env.entries)
    after = env.guard.reconcile(env.entries)
    assert before.digest != after.digest
    assert after.ready


def test_report_to_dict_exposes_component_evidence():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    report = env.guard.inspect(env.entries)
    data = report.to_dict()
    assert data["state"] == "ready"
    assert data["ready"] is True
    assert data["blocked"] is False
    assert data["operations"]["allowed"] is True
    assert data["sequence_indexes"]["ok"] is True
    assert data["verification"]["ok"] is True
    assert data["digest"] == report.digest


@pytest.mark.parametrize(
    "field",
    [
        "require_operations_allowed",
        "require_sequence_indexes",
        "require_verification_current",
        "allow_sequence_index_repair",
        "allow_verification_refresh",
        "require_nonempty_chains",
    ],
)
def test_readiness_policy_bool_validation(field):
    values = {
        "require_operations_allowed": True,
        "require_sequence_indexes": True,
        "require_verification_current": True,
        "allow_sequence_index_repair": True,
        "allow_verification_refresh": True,
        "require_nonempty_chains": True,
    }
    values[field] = "yes"
    with pytest.raises(ValueError, match="bool"):
        DurableEvidenceReadinessPolicy(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_chains", 0),
        ("max_findings", 0),
        ("max_chains", True),
        ("max_findings", 1.5),
    ],
)
def test_readiness_policy_positive_integer_validation(
    field,
    value,
):
    values = {
        "max_chains": 32,
        "max_findings": 256,
    }
    values[field] = value
    with pytest.raises(ValueError):
        DurableEvidenceReadinessPolicy(**values)


def test_policy_digest_is_deterministic():
    first = DurableEvidenceReadinessPolicy()
    second = DurableEvidenceReadinessPolicy()
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_policy_digest_changes_with_behavior():
    first = DurableEvidenceReadinessPolicy()
    second = DurableEvidenceReadinessPolicy(
        allow_verification_refresh=False,
    )
    assert first.digest != second.digest


def test_policy_to_dict():
    policy = DurableEvidenceReadinessPolicy(
        require_operations_allowed=False,
        require_sequence_indexes=False,
        require_verification_current=False,
        allow_sequence_index_repair=False,
        allow_verification_refresh=False,
        require_nonempty_chains=False,
        max_chains=2,
        max_findings=5,
    )
    assert policy.to_dict() == {
        "require_operations_allowed": False,
        "require_sequence_indexes": False,
        "require_verification_current": False,
        "allow_sequence_index_repair": False,
        "allow_verification_refresh": False,
        "require_nonempty_chains": False,
        "max_chains": 2,
        "max_findings": 5,
    }


def test_finding_validation():
    with pytest.raises(ValueError, match="code"):
        DurableEvidenceReadinessFinding(
            "warning",
            "",
            "message",
        )
    with pytest.raises(ValueError, match="message"):
        DurableEvidenceReadinessFinding(
            "warning",
            "code",
            "",
        )
    with pytest.raises(ValueError, match="chain_id"):
        DurableEvidenceReadinessFinding(
            "warning",
            "code",
            "message",
            "x" * 129,
        )


def test_finding_accepts_string_severity():
    finding = DurableEvidenceReadinessFinding(
        "warning",
        "code",
        "message",
    )
    assert (
        finding.severity
        is DurableEvidenceReadinessSeverity.WARNING
    )


def test_finding_to_dict():
    finding = DurableEvidenceReadinessFinding(
        "error",
        "code",
        "message",
        "journal",
    )
    assert finding.to_dict() == {
        "severity": "error",
        "code": "code",
        "message": "message",
        "chain_id": "journal",
    }


def minimal_report(
    state=DurableEvidenceReadinessState.READY,
    *,
    findings=(),
    mutations=(),
):
    return DurableEvidenceReadinessReport(
        state,
        fp("policy"),
        ("journal",),
        None,
        None,
        None,
        None,
        mutations,
        findings,
    )


def test_readiness_report_state_properties():
    ready = minimal_report()
    assert ready.ready
    assert not ready.degraded
    assert not ready.blocked

    degraded = minimal_report(
        DurableEvidenceReadinessState.DEGRADED
    )
    assert degraded.degraded
    assert not degraded.ready
    assert not degraded.blocked

    blocked = minimal_report(
        DurableEvidenceReadinessState.BLOCKED
    )
    assert blocked.blocked

    error = minimal_report(
        DurableEvidenceReadinessState.ERROR
    )
    assert error.blocked


def test_readiness_report_counts_findings():
    report = minimal_report(
        DurableEvidenceReadinessState.BLOCKED,
        findings=(
            DurableEvidenceReadinessFinding(
                "error",
                "a",
                "a",
            ),
            DurableEvidenceReadinessFinding(
                "warning",
                "b",
                "b",
            ),
        ),
    )
    assert report.errors == 1
    assert report.warnings == 1


def test_readiness_report_repaired_property():
    assert not minimal_report().repaired
    assert minimal_report(
        mutations=("sequence_index_repair",)
    ).repaired


def test_readiness_report_rejects_unsorted_chain_ids():
    with pytest.raises(ValueError, match="sorted"):
        DurableEvidenceReadinessReport(
            "ready",
            fp("policy"),
            ("z", "a"),
            None,
            None,
            None,
            None,
            (),
            (),
        )


def test_readiness_report_rejects_duplicate_chain_ids():
    with pytest.raises(ValueError, match="duplicate"):
        DurableEvidenceReadinessReport(
            "ready",
            fp("policy"),
            ("a", "a"),
            None,
            None,
            None,
            None,
            (),
            (),
        )


def test_readiness_report_rejects_duplicate_mutations():
    with pytest.raises(ValueError, match="duplicate"):
        DurableEvidenceReadinessReport(
            "ready",
            fp("policy"),
            ("a",),
            None,
            None,
            None,
            None,
            ("repair", "repair"),
            (),
        )


def test_readiness_report_rejects_bad_policy_digest():
    with pytest.raises(ValueError, match="policy_digest"):
        DurableEvidenceReadinessReport(
            "ready",
            "bad",
            ("a",),
            None,
            None,
            None,
            None,
            (),
            (),
        )


def test_guard_constructor_validation():
    env = Environment()
    with pytest.raises(TypeError, match="operations"):
        DurableEvidenceReadinessGuard(
            object(),
            env.sequence_indexes,
            env.verification,
        )
    with pytest.raises(TypeError, match="sequence_indexes"):
        DurableEvidenceReadinessGuard(
            env.operations,
            object(),
            env.verification,
        )
    with pytest.raises(TypeError, match="verification"):
        DurableEvidenceReadinessGuard(
            env.operations,
            env.sequence_indexes,
            object(),
        )
    with pytest.raises(TypeError, match="policy"):
        DurableEvidenceReadinessGuard(
            env.operations,
            env.sequence_indexes,
            env.verification,
            object(),
        )


def test_entries_reject_invalid_shape():
    env = Environment()
    with pytest.raises(ValueError, match="pairs"):
        env.guard.inspect(("bad",))


def test_entries_reject_duplicate_ids():
    env = Environment()
    with pytest.raises(ValueError, match="duplicate"):
        env.guard.inspect(
            (
                ("same", env.journal),
                ("same", env.receipts),
            )
        )


def test_entries_reject_bad_id():
    env = Environment()
    with pytest.raises(ValueError, match="chain_id"):
        env.guard.inspect(
            (("", env.journal),)
        )


def test_entries_enforce_chain_bound():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            max_chains=1,
        )
    )
    with pytest.raises(
        DurableEvidenceReadinessError,
        match="bound",
    ):
        env.guard.inspect(env.entries)


def test_operations_unknown_protected_root_becomes_blocked():
    env = Environment()
    env.append(1)
    env.initialize_verification()
    report = env.guard.inspect(
        env.entries,
        protected_roots={
            "unknown": (fp("root"),),
        },
    )
    assert report.blocked
    assert any(
        item.code == "readiness.operations_error"
        for item in report.findings
    )


def test_sequence_sample_failure_blocks_readiness():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    items = env.receipts.snapshot()
    key = env.receipts._sequence_key(2)
    record = env.backend.get(
        "receipts",
        key,
    )
    env.backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            2,
            items[0].receipt_hash,
        ),
    )
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert report.sequence_indexes.corrupt == 1


def test_reconcile_is_idempotent_when_already_ready():
    env = Environment()
    env.append(2)
    env.initialize_verification()
    first = env.guard.reconcile(env.entries)
    second = env.guard.reconcile(env.entries)
    assert first.ready
    assert second.ready
    assert first.mutations == ()
    assert second.mutations == ()


def test_readiness_survives_fresh_guard_instances():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    fresh_sequence = DurableSequenceIndexOperator(
        env.sequence_indexes.policy
    )
    fresh_verification = DurableVerificationOperator(
        env.cursor_store,
        env.incremental,
        env.verification.policy,
    )
    fresh = DurableEvidenceReadinessGuard(
        env.operations,
        fresh_sequence,
        fresh_verification,
        env.guard.policy,
    )
    report = fresh.require_ready(env.entries)
    assert report.ready


def test_checkpoint_publish_does_not_break_ready_state():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    env.checkpoints.publish(
        "journal",
        env.journal,
    )
    env.checkpoints.publish(
        "receipts",
        env.receipts,
    )
    report = env.guard.inspect(env.entries)
    assert report.ready


def test_readiness_after_more_work_and_reconcile():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    for _ in range(4):
        env.append(1)
        report = env.guard.reconcile(env.entries)
        assert report.ready
        assert (
            "verification_full_refresh"
            in report.mutations
        )


def test_report_mutation_order_is_deterministic():
    env = Environment()
    env.append(3)
    env.initialize_verification()
    key = env.receipts._sequence_key(1)
    record = env.backend.get(
        "receipts",
        key,
    )
    env.backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    env.append(1)
    report = env.guard.reconcile(env.entries)
    assert report.mutations == (
        "sequence_index_repair",
        "verification_full_refresh",
    )
