"""Unified durable evidence readiness and reconciliation tests."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_proof_window import (
    DurableHistoricalProofAuthority,
    DurableHistoricalProofStore,
)
from skeleton.shells.ai.durable_proof_window_operator import (
    DurableProofWindowOperator,
    DurableProofWindowPolicy,
)
from skeleton.shells.ai.durable_orphan_scan import (
    DurableOrphanScanner,
)
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
from skeleton.shells.ai.journal import (
    AIDecisionEvent,
    AIDecisionJournal,
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
        orphan_scanner=None,
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
            orphan_scanner=orphan_scanner,
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

def inject_journal_orphan(
    env: Environment,
    *,
    name: str = "orphan",
):
    payload = MappingProxyType({"name": name})
    digest = AIDecisionJournal._hash(
        "0" * 64,
        1,
        f"orphan.{name}",
        11.0,
        f"orphan-session-{name}",
        f"orphan-intent-{name}",
        "",
        name,
        payload,
    )
    event = AIDecisionEvent(
        1,
        "0" * 64,
        digest,
        f"orphan.{name}",
        11.0,
        f"orphan-session-{name}",
        f"orphan-intent-{name}",
        "",
        name,
        payload,
    )
    env.backend.put_if_absent(
        env.journal.namespace,
        env.journal._event_key(digest),
        event,
    )
    return event


def test_orphan_scanner_keeps_clean_initialized_readiness_ready():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
    )
    env.append(2)
    env.initialize_verification()
    report = env.guard.inspect(env.entries)
    assert report.ready
    journal_report = next(
        item
        for item in report.operations.chains
        if item.chain_id == "journal"
    )
    assert journal_report.orphan_scan is not None
    assert journal_report.orphan_scan.orphan_candidates == 0
    assert journal_report.orphan_scan.healthy


def test_orphan_candidate_degrades_readiness_without_blocking():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
    )
    env.append(2)
    env.initialize_verification()
    orphan = inject_journal_orphan(env)
    report = env.guard.inspect(env.entries)
    assert report.degraded
    assert not report.blocked
    assert report.operations.allowed
    assert report.operations.warnings >= 1
    journal_report = next(
        item
        for item in report.operations.chains
        if item.chain_id == "journal"
    )
    assert journal_report.orphan_scan.orphan_candidates == 1
    assert (
        journal_report.orphan_scan
        .safe_delete_candidates[0]
        .node_hash
        == orphan.event_hash
    )
    assert any(
        item.code == "durable_orphan.candidates"
        for item in journal_report.findings
    )
    assert any(
        item.code == "readiness.operations_warning"
        for item in report.findings
    )


def test_orphan_index_conflict_blocks_readiness():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
    )
    env.append(2)
    env.initialize_verification()
    orphan = inject_journal_orphan(env)
    key = env.journal._sequence_key(1)
    record = env.backend.get(
        env.journal.namespace,
        key,
    )
    env.backend.compare_and_swap(
        env.journal.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            orphan.event_hash,
        ),
    )
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert not report.operations.allowed
    journal_report = next(
        item
        for item in report.operations.chains
        if item.chain_id == "journal"
    )
    assert journal_report.orphan_scan.requires_manual_review
    assert journal_report.orphan_scan.index_conflicts == 1
    assert any(
        item.code == "durable_orphan.manual_review"
        for item in journal_report.findings
    )


def test_corrupt_orphan_record_blocks_readiness():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
    )
    env.append(2)
    env.initialize_verification()
    env.backend.put_if_absent(
        env.journal.namespace,
        "event:" + ("f" * 64),
        {"bad": True},
    )
    report = env.guard.inspect(env.entries)
    assert report.blocked
    journal_report = next(
        item
        for item in report.operations.chains
        if item.chain_id == "journal"
    )
    assert journal_report.orphan_scan.corrupt == 1
    assert any(
        item.code == "durable_orphan.manual_review"
        for item in journal_report.findings
    )


def test_required_orphan_scan_without_scanner_blocks_readiness():
    env = Environment(
        operations_policy=DurableOperationsPolicy(
            require_orphan_scan=True,
        ),
    )
    env.append(2)
    env.initialize_verification()
    report = env.guard.inspect(env.entries)
    assert report.blocked
    assert not report.operations.allowed
    assert all(
        any(
            finding.code == "durable_orphan.scan_required"
            for finding in chain.findings
        )
        for chain in report.operations.chains
    )


def test_disabling_orphan_candidate_warning_keeps_readiness_ready():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
        operations_policy=DurableOperationsPolicy(
            warn_on_orphan_candidates=False,
        ),
    )
    env.append(2)
    env.initialize_verification()
    inject_journal_orphan(env)
    report = env.guard.inspect(env.entries)
    assert report.ready
    journal_report = next(
        item
        for item in report.operations.chains
        if item.chain_id == "journal"
    )
    assert journal_report.orphan_scan.orphan_candidates == 1
    assert not any(
        item.code == "durable_orphan.candidates"
        for item in journal_report.findings
    )


def test_orphan_scan_is_serialized_in_readiness_operations_report():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
    )
    env.append(1)
    env.initialize_verification()
    inject_journal_orphan(env)
    report = env.guard.inspect(env.entries)
    data = report.to_dict()
    journal = next(
        item
        for item in data["operations"]["chains"]
        if item["chain_id"] == "journal"
    )
    assert journal["orphan_scan"] is not None
    assert journal["orphan_scan"]["orphan_candidates"] == 1
    assert len(journal["orphan_scan"]["digest"]) == 64


def test_require_ready_rejects_degraded_orphan_pressure():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
    )
    env.append(1)
    env.initialize_verification()
    inject_journal_orphan(env)
    with pytest.raises(
        DurableEvidenceReadinessError,
        match="warning",
    ):
        env.guard.require_ready(env.entries)


def test_readiness_digest_changes_when_orphan_appears():
    env = Environment(
        orphan_scanner=DurableOrphanScanner(
            clock=lambda: 100.0,
        ),
    )
    env.append(1)
    env.initialize_verification()
    before = env.guard.inspect(env.entries)
    inject_journal_orphan(env)
    after = env.guard.inspect(env.entries)
    assert before.digest != after.digest
    assert before.ready
    assert after.degraded

class ProofEnvironment(Environment):
    def __init__(
        self,
        *,
        readiness_policy=None,
        proof_policy=None,
    ):
        super().__init__(
            readiness_policy=readiness_policy
        )
        self.proof_store = DurableHistoricalProofStore(
            self.backend,
            namespace="proof-windows",
        )
        self.proof_authority = DurableHistoricalProofAuthority(
            self.checkpoints,
            ArtifactSigner(
                "proof-window",
                b"p" * 32,
                clock=lambda: 100.0,
            ),
            max_window_items=32,
            clock=lambda: 100.0,
        )
        self.proof_operator = DurableProofWindowOperator(
            self.proof_authority,
            self.proof_store,
            {
                "journal": self.journal,
                "receipts": self.receipts,
            },
            policy=(
                proof_policy
                or DurableProofWindowPolicy(
                    max_targets=16,
                )
            ),
        )
        self.guard = DurableEvidenceReadinessGuard(
            self.operations,
            self.sequence_indexes,
            self.verification,
            readiness_policy,
            proof_windows=self.proof_operator,
        )

    def publish_checkpoints(self):
        return (
            self.checkpoints.publish(
                "journal",
                self.journal,
            ),
            self.checkpoints.publish(
                "receipts",
                self.receipts,
            ),
        )


def proof_protected_roots(env):
    return {
        "journal": (
            env.journal.root_hash(),
        ),
        "receipts": (
            env.receipts.root_hash(),
        ),
    }


def test_required_proof_windows_block_when_operator_is_absent():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.initialize_verification()
    report = env.guard.inspect(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    assert report.blocked
    assert any(
        item.code
        == "readiness.proof_windows_unavailable"
        for item in report.findings
    )


def test_optional_proof_windows_do_not_require_operator():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=False,
        )
    )
    env.append(2)
    env.initialize_verification()
    report = env.guard.inspect(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    assert report.ready
    assert report.proof_windows is None


def test_required_proof_windows_missing_cache_blocks_inspection():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    env.initialize_verification()
    report = env.guard.inspect(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    assert report.blocked
    assert report.proof_windows is not None
    assert report.proof_windows.missing == 2
    assert any(
        item.code
        == "readiness.proof_windows_unhealthy"
        for item in report.findings
    )


def test_reconcile_builds_missing_required_proof_windows():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
            allow_proof_window_build=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    report = env.guard.reconcile(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    assert report.ready
    assert report.proof_windows is not None
    assert report.proof_windows.ok
    assert report.proof_windows.current == 2
    assert "proof_window_build" in report.mutations
    assert "verification_full_refresh" in report.mutations


def test_reconcile_proof_build_is_idempotent():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
            allow_proof_window_build=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    roots = proof_protected_roots(env)
    first = env.guard.reconcile(
        env.entries,
        protected_roots=roots,
    )
    second = env.guard.reconcile(
        env.entries,
        protected_roots=roots,
    )
    assert first.ready
    assert second.ready
    assert "proof_window_build" in first.mutations
    assert "proof_window_build" not in second.mutations
    assert second.proof_windows.ok


def test_disabled_proof_build_blocks_required_reconcile():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
            allow_proof_window_build=False,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    with pytest.raises(
        DurableEvidenceReadinessError,
        match="proof-window build",
    ):
        env.guard.reconcile(
            env.entries,
            protected_roots=proof_protected_roots(
                env
            ),
        )


def test_optional_missing_proof_windows_degrade_not_block():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=False,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    env.initialize_verification()
    report = env.guard.inspect(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    assert report.degraded
    assert not report.blocked
    assert report.warnings == 1
    assert report.proof_windows.missing == 2


def test_optional_reconcile_can_build_proof_windows_to_ready():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=False,
            allow_proof_window_build=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    report = env.guard.reconcile(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    assert report.ready
    assert report.proof_windows.ok
    assert "proof_window_build" in report.mutations


def test_no_protected_roots_need_no_proof_windows():
    env = Environment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.initialize_verification()
    report = env.guard.inspect(
        env.entries
    )
    assert report.ready
    assert report.proof_windows is None


def test_checkpoint_root_can_use_zero_length_proof():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.initialize_verification()
    report = env.guard.reconcile(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    assert report.ready
    assert all(
        item.checked_items == 0
        for item in report.proof_windows.reports
    )


def test_protected_root_deduplication_does_not_duplicate_targets():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    env.initialize_verification()
    roots = {
        "journal": (
            env.journal.root_hash(),
            env.journal.root_hash(),
        ),
        "receipts": (
            env.receipts.root_hash(),
            env.receipts.root_hash(),
        ),
    }
    report = env.guard.reconcile(
        env.entries,
        protected_roots=roots,
    )
    assert report.ready
    assert len(
        report.proof_windows.reports
    ) == 2


def test_proof_window_report_is_serialized_in_readiness():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    report = env.guard.reconcile(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
    )
    data = report.to_dict()
    assert data["proof_windows"] is not None
    assert data["proof_windows"]["ok"] is True
    assert len(
        data["proof_windows"]["reports"]
    ) == 2


def test_readiness_digest_binds_proof_window_state():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=False,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    env.initialize_verification()
    roots = proof_protected_roots(env)
    before = env.guard.inspect(
        env.entries,
        protected_roots=roots,
    )
    after = env.guard.reconcile(
        env.entries,
        protected_roots=roots,
    )
    assert before.digest != after.digest
    assert before.proof_windows.missing == 2
    assert after.proof_windows.ok


def test_corrupt_cached_proof_blocks_when_required():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    env.initialize_verification()
    roots = proof_protected_roots(env)
    ready = env.guard.reconcile(
        env.entries,
        protected_roots=roots,
    )
    assert ready.ready
    target = ready.proof_windows.reports[0].target
    item = env.proof_store.find_target(
        target.chain_id,
        target.target_root,
    )
    key = env.proof_store._proof_key(
        item.proof.digest
    )
    record = env.backend.get(
        "proof-windows",
        key,
    )
    env.backend.compare_and_swap(
        "proof-windows",
        key,
        expected_revision=record.revision,
        value=replace(
            item,
            signature=replace(
                item.signature,
                signature="0" * 64,
            ),
        ),
    )
    report = env.guard.inspect(
        env.entries,
        protected_roots=roots,
    )
    assert report.blocked
    assert report.proof_windows.invalid >= 1


def test_corrupt_cached_proof_is_not_overwritten_by_reconcile():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        ),
        proof_policy=DurableProofWindowPolicy(
            refresh_invalid=True,
        ),
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    roots = proof_protected_roots(env)
    ready = env.guard.reconcile(
        env.entries,
        protected_roots=roots,
    )
    target = ready.proof_windows.reports[0].target
    item = env.proof_store.find_target(
        target.chain_id,
        target.target_root,
    )
    key = env.proof_store._proof_key(
        item.proof.digest
    )
    record = env.backend.get(
        "proof-windows",
        key,
    )
    env.backend.compare_and_swap(
        "proof-windows",
        key,
        expected_revision=record.revision,
        value=replace(
            item,
            signature=replace(
                item.signature,
                signature="0" * 64,
            ),
        ),
    )
    report = env.guard.reconcile(
        env.entries,
        protected_roots=roots,
    )
    assert report.blocked
    assert report.proof_windows.invalid + report.proof_windows.errors >= 1


def test_guard_rejects_wrong_proof_window_operator_type():
    env = Environment()
    with pytest.raises(
        TypeError,
        match="proof_windows",
    ):
        DurableEvidenceReadinessGuard(
            env.operations,
            env.sequence_indexes,
            env.verification,
            proof_windows=object(),
        )


@pytest.mark.parametrize(
    "field",
    [
        "require_proof_windows",
        "allow_proof_window_build",
    ],
)
def test_readiness_policy_validates_proof_window_bools(field):
    values = dict(
        require_proof_windows=False,
        allow_proof_window_build=True,
    )
    values[field] = "yes"
    with pytest.raises(ValueError):
        DurableEvidenceReadinessPolicy(
            **values
        )


def test_policy_digest_changes_with_proof_window_requirement():
    optional = DurableEvidenceReadinessPolicy(
        require_proof_windows=False,
    )
    required = DurableEvidenceReadinessPolicy(
        require_proof_windows=True,
    )
    assert optional.digest != required.digest


def test_policy_to_dict_exposes_proof_window_controls():
    policy = DurableEvidenceReadinessPolicy(
        require_proof_windows=True,
        allow_proof_window_build=False,
    )
    data = policy.to_dict()
    assert data["require_proof_windows"] is True
    assert data["allow_proof_window_build"] is False


def test_require_ready_can_reconcile_required_proofs():
    env = ProofEnvironment(
        readiness_policy=DurableEvidenceReadinessPolicy(
            require_proof_windows=True,
        )
    )
    env.append(2)
    env.publish_checkpoints()
    env.append(1)
    report = env.guard.require_ready(
        env.entries,
        protected_roots=proof_protected_roots(
            env
        ),
        reconcile=True,
    )
    assert report.ready
    assert report.proof_windows.ok
