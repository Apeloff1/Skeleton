"""Replica-aware durable evidence readiness and recovery tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_operations import (
    DurableEvidenceOperationsInspector,
    DurableOperationsPolicy,
)
from skeleton.shells.ai.durable_readiness import (
    DurableEvidenceReadinessGuard,
    DurableEvidenceReadinessPolicy,
)
from skeleton.shells.ai.durable_replica_consensus import (
    DurableReplicaConsensusEvaluator,
    DurableReplicaConsensusPolicy,
)
from skeleton.shells.ai.durable_replica_consensus_history import (
    DurableReplicaConsensusHistoryStore,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetMember,
    DurableReplicaFleetPolicy,
)
from skeleton.shells.ai.durable_replica_readiness import (
    DurableReplicaReadinessError,
    DurableReplicaReadinessFinding,
    DurableReplicaReadinessGuard,
    DurableReplicaReadinessPolicy,
    DurableReplicaReadinessReport,
    DurableReplicaReadinessSeverity,
    DurableReplicaReadinessState,
)
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicator,
    DurableEvidenceReplicaManager,
    DurableReplicationPolicy,
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
)
from skeleton.shells.ai.durable_verification_operator import (
    DurableVerificationOperator,
    DurableVerificationOperatorPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


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
    )


class Replica:
    def __init__(
        self,
        target_id: str,
        failure_domain: str,
        journal,
        receipts,
        *,
        clock,
        required=False,
    ):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            clock=clock,
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
        )
        policy = DurableReplicationPolicy(
            max_batch_items=4,
            max_batches_per_run=32,
        )
        self.manager = DurableEvidenceReplicaManager(
            DurableChainReplicator(
                "journal",
                journal,
                self.journal,
                policy=policy,
            ),
            DurableChainReplicator(
                "receipts",
                receipts,
                self.receipts,
                policy=policy,
            ),
            policy=policy,
        )
        self.member = DurableReplicaFleetMember(
            target_id,
            failure_domain,
            self.manager,
            required=required,
        )


class Environment:
    def __init__(
        self,
        *,
        sync=True,
        initialize_local=True,
        replica_policy=None,
        with_history=True,
    ):
        self.now = [100.0]
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            max_events=1000,
            clock=lambda: self.now[0],
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
            max_receipts=1000,
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            ArtifactSigner(
                "checkpoint",
                b"c" * 32,
                clock=lambda: self.now[0],
            ),
            namespace="checkpoints",
            clock=lambda: self.now[0],
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
            policy=DurableOperationsPolicy(),
        )
        self.cursor_store = DurableVerificationCursorStore(
            self.backend,
            ArtifactSigner(
                "cursor",
                b"v" * 32,
                clock=lambda: self.now[0],
            ),
            namespace="cursors",
        )
        self.incremental = DurableIncrementalVerifier(
            self.cursor_store,
            clock=lambda: self.now[0],
        )
        self.verification = DurableVerificationOperator(
            self.cursor_store,
            self.incremental,
            DurableVerificationOperatorPolicy(
                max_chains=8,
                max_lineage_items=2048,
            ),
        )
        self.sequence_indexes = DurableSequenceIndexOperator(
            DurableSequenceIndexPolicy(
                max_items_per_chain=5000,
                max_chains=8,
                sample_window_items=8,
            )
        )
        self.local = DurableEvidenceReadinessGuard(
            self.operations,
            self.sequence_indexes,
            self.verification,
            DurableEvidenceReadinessPolicy(),
        )

        self.append(3)
        if initialize_local:
            self.verification.force_full_refresh(
                self.entries
            )

        self.replicas = {
            "replica-a": Replica(
                "replica-a",
                "zone-a",
                self.journal,
                self.receipts,
                clock=lambda: self.now[0],
            ),
            "replica-b": Replica(
                "replica-b",
                "zone-b",
                self.journal,
                self.receipts,
                clock=lambda: self.now[0],
            ),
            "replica-c": Replica(
                "replica-c",
                "zone-c",
                self.journal,
                self.receipts,
                clock=lambda: self.now[0],
            ),
        }
        self.fleet = DurableReplicaFleet(
            "primary",
            tuple(
                item.member
                for item in self.replicas.values()
            ),
            policy=DurableReplicaFleetPolicy(
                min_ready_replicas=2,
                min_ready_failure_domains=2,
            ),
            clock=lambda: self.now[0],
        )
        if sync:
            self.fleet.sync_all()

        self.consensus = DurableReplicaConsensusEvaluator(
            DurableReplicaConsensusPolicy(
                min_agreeing_replicas=2,
                min_agreeing_failure_domains=2,
                min_agreement_fraction=2.0 / 3.0,
            )
        )
        self.history = (
            DurableReplicaConsensusHistoryStore(
                self.backend,
                namespace="consensus-history",
                clock=lambda: self.now[0],
            )
            if with_history
            else None
        )
        self.replica_policy = (
            replica_policy
            or DurableReplicaReadinessPolicy()
        )
        self.guard = DurableReplicaReadinessGuard(
            self.local,
            self.fleet,
            self.consensus,
            journal_chain=self.journal,
            receipt_chain=self.receipts,
            history=self.history,
            policy=self.replica_policy,
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
            self.journal.append(
                "replica-readiness.event",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
            )
            self.receipts.append(
                make_receipt(index)
            )

    def refresh_local(self):
        return self.verification.force_full_refresh(
            self.entries
        )

    def sync_all(self):
        return self.fleet.sync_all()

    def advance_all(self):
        self.now[0] += 1
        self.append()
        self.refresh_local()
        self.sync_all()


def test_ready_when_local_fleet_and_consensus_are_healthy():
    env = Environment()
    report = env.guard.inspect(
        env.entries
    )
    assert report.ready
    assert report.state is DurableReplicaReadinessState.READY
    assert report.errors == 0
    assert report.warnings == 0
    assert report.local.ready
    assert report.fleet.quorum_ready
    assert report.consensus.certifiable
    assert report.history is None


def test_require_ready_returns_composed_report():
    env = Environment()
    report = env.guard.require_ready(
        env.entries
    )
    assert report.ready
    assert report.consensus.selected is not None


def test_local_not_ready_blocks_replica_readiness():
    env = Environment(
        initialize_local=False
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.blocked
    assert any(
        item.code
        == "replica_readiness.local_not_ready"
        for item in report.findings
    )


def test_local_not_ready_can_be_degraded_by_policy():
    env = Environment(
        initialize_local=False,
        replica_policy=DurableReplicaReadinessPolicy(
            require_local_ready=False,
        ),
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.degraded
    assert report.warnings >= 1


def test_unsynchronized_fleet_blocks_readiness():
    env = Environment(
        sync=False
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.blocked
    assert any(
        item.code
        == "replica_readiness.fleet_quorum_unready"
        for item in report.findings
    )


def test_fleet_quorum_can_be_warning_by_policy():
    env = Environment(
        sync=False,
        replica_policy=DurableReplicaReadinessPolicy(
            require_fleet_quorum=False,
            require_consensus=False,
        ),
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.degraded
    assert report.warnings >= 1


def test_consensus_split_brain_blocks_readiness():
    env = Environment()
    rogue_backend = InMemoryFencedStore()
    rogue_journal = DistributedAIDecisionJournal(
        rogue_backend,
        namespace="journal",
        clock=lambda: env.now[0],
    )
    rogue_receipts = DistributedReceiptChain(
        rogue_backend,
        namespace="receipts",
    )
    for index in range(1, 5):
        rogue_journal.append(
            f"rogue.{index}",
            session_id=f"rogue-{index}",
            intent_id=f"rogue-intent-{index}",
            proposal_id=f"rogue-proposal-{index}",
        )
        rogue_receipts.append(
            make_receipt(index + 10)
        )
    rogue = Replica(
        "replica-c",
        "zone-c",
        rogue_journal,
        rogue_receipts,
        clock=lambda: env.now[0],
    )
    rogue.manager.sync()
    env.fleet = DurableReplicaFleet(
        "primary",
        (
            env.replicas["replica-a"].member,
            env.replicas["replica-b"].member,
            rogue.member,
        ),
        policy=DurableReplicaFleetPolicy(
            min_ready_replicas=2,
            min_ready_failure_domains=2,
        ),
        clock=lambda: env.now[0],
    )
    guard = DurableReplicaReadinessGuard(
        env.local,
        env.fleet,
        env.consensus,
        journal_chain=env.journal,
        receipt_chain=env.receipts,
        history=env.history,
    )
    report = guard.inspect(
        env.entries
    )
    assert report.blocked
    assert report.consensus.split_brain
    assert any(
        item.code
        == "replica_readiness.consensus_unhealthy"
        for item in report.findings
    )


def test_consensus_failure_can_be_warning_by_policy():
    env = Environment()
    policy = DurableReplicaReadinessPolicy(
        require_consensus=False,
    )
    # Replace consensus evaluator with a policy impossible for this 3-member
    # fleet by requiring four agreeing replicas.
    impossible = DurableReplicaConsensusEvaluator(
        DurableReplicaConsensusPolicy(
            min_agreeing_replicas=4,
            min_agreeing_failure_domains=2,
            min_agreement_fraction=2.0 / 3.0,
        )
    )
    guard = DurableReplicaReadinessGuard(
        env.local,
        env.fleet,
        impossible,
        journal_chain=env.journal,
        receipt_chain=env.receipts,
        history=env.history,
        policy=policy,
    )
    report = guard.inspect(
        env.entries
    )
    assert report.degraded
    assert any(
        item.severity
        is DurableReplicaReadinessSeverity.WARNING
        for item in report.findings
    )


def test_optional_empty_history_does_not_block_initial_readiness():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=False,
        ),
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.ready
    assert report.history is None


def test_required_initialized_history_blocks_before_first_reconcile():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.blocked
    assert any(
        item.code
        == "replica_readiness.history_uninitialized"
        for item in report.findings
    )


def test_reconcile_initializes_consensus_history():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    report = env.guard.reconcile(
        env.entries
    )
    assert report.ready
    assert report.repaired
    assert (
        "consensus_history_record"
        in report.mutations
    )
    assert report.history is not None
    assert (
        report.consensus_history_generation
        == 1
    )


def test_reconcile_history_is_idempotent():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    first = env.guard.reconcile(
        env.entries
    )
    second = env.guard.reconcile(
        env.entries
    )
    assert first.ready
    assert second.ready
    assert (
        "consensus_history_record"
        in first.mutations
    )
    assert (
        "consensus_history_record"
        not in second.mutations
    )
    assert second.history.epoch.generation == 1


def test_source_growth_blocks_against_old_history_after_replicas_resync():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    env.guard.reconcile(
        env.entries
    )
    env.advance_all()
    report = env.guard.inspect(
        env.entries
    )
    assert report.blocked
    assert any(
        item.code
        == "replica_readiness.history_not_current"
        for item in report.findings
    )


def test_explicit_reconcile_advances_history_after_source_growth():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    first = env.guard.reconcile(
        env.entries
    )
    env.advance_all()
    second = env.guard.reconcile(
        env.entries
    )
    assert second.ready
    assert (
        second.consensus_history_generation
        == 2
    )
    assert (
        second.history.epoch.previous_digest
        == first.history.epoch.digest
    )


def test_reconcile_never_synchronizes_unready_fleet_implicitly():
    env = Environment(
        sync=False,
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    report = env.guard.reconcile(
        env.entries
    )
    assert report.blocked
    assert env.fleet.inspect().blocked
    assert env.history.current(
        "primary"
    ) is None


def test_explicit_fleet_sync_then_reconcile_can_become_ready():
    env = Environment(
        sync=False,
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    assert env.guard.inspect(
        env.entries
    ).blocked
    env.sync_all()
    report = env.guard.reconcile(
        env.entries
    )
    assert report.ready
    assert report.history is not None


def test_history_store_can_be_required_at_construction():
    with pytest.raises(
        ValueError,
        match="requires consensus history store",
    ):
        env = Environment(
            with_history=False,
            replica_policy=DurableReplicaReadinessPolicy(
                require_history_store=True,
            ),
        )
        assert env


def test_no_history_store_is_allowed_by_default():
    env = Environment(
        with_history=False
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.ready
    assert report.history is None


def test_history_corruption_blocks_readiness():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    ready = env.guard.reconcile(
        env.entries
    )
    current = ready.history
    key = env.history._epoch_key(
        current.epoch.digest
    )
    record = env.backend.get(
        env.history.namespace,
        key,
    )
    env.backend.compare_and_swap(
        env.history.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            current.epoch,
            fleet_state_digest=fp("9"),
        ),
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.blocked
    assert any(
        item.code
        in {
            "replica_readiness.history_error",
            "replica_readiness.history_not_current",
        }
        for item in report.findings
    )


def test_require_ready_raises_when_history_is_stale():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    env.guard.reconcile(
        env.entries
    )
    env.advance_all()
    with pytest.raises(
        DurableReplicaReadinessError,
        match="history",
    ):
        env.guard.require_ready(
            env.entries
        )


def test_report_serialization_contains_all_layers():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    report = env.guard.reconcile(
        env.entries
    )
    data = report.to_dict()
    assert data["state"] == "ready"
    assert data["local"]["ready"] is True
    assert data["fleet"]["quorum_ready"] is True
    assert data["consensus"]["certifiable"] is True
    assert data["history"] is not None
    assert (
        data["consensus_history_generation"]
        == 1
    )
    assert data["digest"] == report.digest


def test_report_digest_binds_history_generation():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    first = env.guard.reconcile(
        env.entries
    )
    env.advance_all()
    second = env.guard.reconcile(
        env.entries
    )
    assert first.digest != second.digest
    assert (
        first.consensus_history_generation
        == 1
    )
    assert (
        second.consensus_history_generation
        == 2
    )


def test_report_digest_is_stable_without_state_change():
    env = Environment()
    first = env.guard.inspect(
        env.entries
    )
    second = env.guard.inspect(
        env.entries
    )
    assert first.digest == second.digest
    assert first == second


@pytest.mark.parametrize(
    "changes",
    [
        {"require_local_ready": "yes"},
        {"require_fleet_quorum": 1},
        {"require_consensus": None},
        {"require_history_store": "yes"},
        {"require_history_initialized": 1},
        {"require_history_current": "yes"},
        {"allow_history_record_on_reconcile": 1},
        {"max_findings": 0},
        {"max_findings": 65537},
    ],
)
def test_policy_validation(changes):
    with pytest.raises(ValueError):
        DurableReplicaReadinessPolicy(
            **changes
        )


def test_policy_rejects_initialized_without_current():
    with pytest.raises(
        ValueError,
        match="implies current",
    ):
        DurableReplicaReadinessPolicy(
            require_history_initialized=True,
            require_history_current=False,
        )


def test_policy_digest_is_deterministic():
    first = DurableReplicaReadinessPolicy()
    second = DurableReplicaReadinessPolicy()
    assert first.digest == second.digest


def test_finding_validation():
    with pytest.raises(ValueError):
        DurableReplicaReadinessFinding(
            DurableReplicaReadinessSeverity.ERROR,
            "",
            "message",
        )
    with pytest.raises(ValueError):
        DurableReplicaReadinessFinding(
            DurableReplicaReadinessSeverity.ERROR,
            "code",
            "",
        )


def test_constructor_requires_local_guard():
    env = Environment()
    with pytest.raises(TypeError, match="local"):
        DurableReplicaReadinessGuard(
            object(),
            env.fleet,
            env.consensus,
            journal_chain=env.journal,
            receipt_chain=env.receipts,
        )


def test_constructor_requires_fleet():
    env = Environment()
    with pytest.raises(TypeError, match="fleet"):
        DurableReplicaReadinessGuard(
            env.local,
            object(),
            env.consensus,
            journal_chain=env.journal,
            receipt_chain=env.receipts,
        )


def test_constructor_requires_consensus_evaluator():
    env = Environment()
    with pytest.raises(TypeError, match="consensus"):
        DurableReplicaReadinessGuard(
            env.local,
            env.fleet,
            object(),
            journal_chain=env.journal,
            receipt_chain=env.receipts,
        )


def test_constructor_requires_history_type():
    env = Environment()
    with pytest.raises(TypeError, match="history"):
        DurableReplicaReadinessGuard(
            env.local,
            env.fleet,
            env.consensus,
            journal_chain=env.journal,
            receipt_chain=env.receipts,
            history=object(),
        )


def test_constructor_requires_chain_root_surface():
    env = Environment()

    class Missing:
        pass

    with pytest.raises(
        TypeError,
        match="journal_chain",
    ):
        DurableReplicaReadinessGuard(
            env.local,
            env.fleet,
            env.consensus,
            journal_chain=Missing(),
            receipt_chain=env.receipts,
        )


def test_report_type_validation():
    env = Environment()
    report = env.guard.inspect(
        env.entries
    )
    with pytest.raises(TypeError, match="local"):
        replace(
            report,
            local=object(),
        )
    with pytest.raises(TypeError, match="fleet"):
        replace(
            report,
            fleet=object(),
        )
    with pytest.raises(TypeError, match="consensus"):
        replace(
            report,
            consensus=object(),
        )
    with pytest.raises(TypeError, match="history"):
        replace(
            report,
            history=object(),
        )


def test_report_duplicate_mutations_are_rejected():
    env = Environment()
    report = env.guard.inspect(
        env.entries
    )
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        replace(
            report,
            mutations=("x", "x"),
        )


def test_required_history_store_without_initialized_requirement_can_start_empty():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_store=True,
            require_history_initialized=False,
        ),
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.ready
    assert report.history is None


def test_reconcile_records_history_even_when_not_required_initialized():
    env = Environment()
    assert env.history.current(
        "primary"
    ) is None
    report = env.guard.reconcile(
        env.entries
    )
    assert report.ready
    assert report.history is not None
    assert (
        "consensus_history_record"
        in report.mutations
    )


def test_reconcile_can_disable_history_recording():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            allow_history_record_on_reconcile=False,
        ),
    )
    report = env.guard.reconcile(
        env.entries
    )
    assert report.ready
    assert report.history is None
    assert (
        "consensus_history_record"
        not in report.mutations
    )


def test_reconcile_preserves_local_mutation_names():
    env = Environment()
    # Force local verification stale by extending both source chains.
    env.append()
    result = env.guard.reconcile(
        env.entries
    )
    assert result.ready
    assert any(
        mutation
        in {
            "verification_refresh",
            "consensus_history_record",
        }
        for mutation in result.mutations
    )


def test_consensus_history_generation_property_none_when_absent():
    env = Environment()
    report = env.guard.inspect(
        env.entries
    )
    assert (
        report.consensus_history_generation
        is None
    )


def test_blocked_report_has_error_count():
    env = Environment(
        sync=False
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.errors >= 1
    assert report.warnings == 0


def test_warning_only_report_is_degraded():
    env = Environment(
        sync=False,
        replica_policy=DurableReplicaReadinessPolicy(
            require_fleet_quorum=False,
            require_consensus=False,
        ),
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.state is DurableReplicaReadinessState.DEGRADED
    assert report.warnings >= 1
    assert report.errors == 0


def test_history_current_policy_can_be_disabled():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_current=False,
        ),
    )
    initial = env.guard.reconcile(
        env.entries
    )
    assert initial.ready
    env.advance_all()
    report = env.guard.inspect(
        env.entries
    )
    assert report.ready
    assert report.history is not None
    assert report.history.epoch.generation == 1


def test_local_report_state_is_preserved_inside_blocked_replica_report():
    env = Environment(
        sync=False
    )
    report = env.guard.inspect(
        env.entries
    )
    assert report.local.ready
    assert report.blocked
    assert not report.fleet.quorum_ready


def test_consensus_report_is_preserved_inside_history_block():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    env.guard.reconcile(
        env.entries
    )
    env.advance_all()
    report = env.guard.inspect(
        env.entries
    )
    assert report.blocked
    assert report.consensus.certifiable
    assert report.history is None


def test_multiple_growth_reconcile_builds_monotonic_history():
    env = Environment(
        replica_policy=DurableReplicaReadinessPolicy(
            require_history_initialized=True,
        ),
    )
    env.guard.reconcile(
        env.entries
    )
    for _ in range(4):
        env.advance_all()
        report = env.guard.reconcile(
            env.entries
        )
        assert report.ready
    lineage = env.history.lineage(
        "primary"
    )
    assert tuple(
        epoch.generation
        for epoch in lineage
    ) == (1, 2, 3, 4, 5)
    assert env.history.verify(
        "primary",
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )
