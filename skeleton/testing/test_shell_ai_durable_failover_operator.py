"""Operator-facing durable failover workflow tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_failover import (
    DurableFailoverAuthority,
    DurableFailoverCoordinator,
    DurableFailoverRegistry,
)
from skeleton.shells.ai.durable_failover_operator import (
    DurableFailoverOperator,
    DurableFailoverOperatorError,
    DurableFailoverOperatorPolicy,
    DurableFailoverOperatorReport,
    DurableFailoverOperatorState,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetMember,
    DurableReplicaFleetPolicy,
)
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicator,
    DurableEvidenceReplicaManager,
    DurableReplicationPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def receipt(index: int) -> ExecutionReceipt:
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


class OperatorEnvironment:
    def __init__(self, *, count=3):
        self.now = [100.0]
        self.source_backend = InMemoryFencedStore()
        self.source_journal = DistributedAIDecisionJournal(
            self.source_backend,
            namespace="journal",
            clock=lambda: self.now[0],
        )
        self.source_receipts = DistributedReceiptChain(
            self.source_backend,
            namespace="receipts",
        )
        for index in range(1, count + 1):
            self.source_journal.append(
                f"event.{index}",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
            )
            self.source_receipts.append(receipt(index))

        self.managers = {}
        self.members = {}
        for target_id, domain in (
            ("replica-a", "zone-a"),
            ("replica-b", "zone-b"),
        ):
            backend = InMemoryFencedStore()
            journal = DistributedAIDecisionJournal(
                backend,
                namespace="journal",
                clock=lambda: self.now[0],
            )
            receipts = DistributedReceiptChain(
                backend,
                namespace="receipts",
            )
            replication_policy = DurableReplicationPolicy(
                max_batch_items=2,
                max_batches_per_run=16,
            )
            manager = DurableEvidenceReplicaManager(
                DurableChainReplicator(
                    "journal",
                    self.source_journal,
                    journal,
                    policy=replication_policy,
                ),
                DurableChainReplicator(
                    "receipts",
                    self.source_receipts,
                    receipts,
                    policy=replication_policy,
                ),
                policy=replication_policy,
            )
            self.managers[target_id] = manager
            self.members[target_id] = DurableReplicaFleetMember(
                target_id,
                domain,
                manager,
            )

        self.fleet = DurableReplicaFleet(
            "primary",
            tuple(self.members.values()),
            policy=DurableReplicaFleetPolicy(
                min_ready_replicas=2,
                min_ready_failure_domains=2,
            ),
            clock=lambda: self.now[0],
        )
        self.registry = DurableFailoverRegistry(
            InMemoryFencedStore(),
            namespace="failover",
            clock=lambda: self.now[0],
        )
        self.authority = DurableFailoverAuthority(
            ArtifactSigner(
                "operator",
                b"k" * 32,
                clock=lambda: self.now[0],
            ),
            clock=lambda: self.now[0],
            nonce_factory=lambda: "operator-nonce",
        )
        self.coordinator = DurableFailoverCoordinator(
            self.managers["replica-a"],
            self.authority,
            self.registry,
            source_id="primary",
            target_id="replica-a",
            fleet=self.fleet,
        )
        self.operator = DurableFailoverOperator(
            self.managers["replica-a"],
            self.coordinator,
            fleet=self.fleet,
            policy=DurableFailoverOperatorPolicy(
                max_batches_per_sync=16,
                require_fleet_quorum=True,
            ),
            clock=lambda: self.now[0],
        )

    def sync_target(self, target_id):
        return self.managers[target_id].sync()

    def sync_all(self):
        return self.fleet.sync_all()

    def advance_source(self):
        index = self.source_journal.length() + 1
        self.source_journal.append(
            f"event.{index}",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
        )
        self.source_receipts.append(receipt(index))


def test_initial_operator_state_needs_sync():
    env = OperatorEnvironment()
    report = env.operator.inspect()
    assert report.state is DurableFailoverOperatorState.NEEDS_SYNC
    assert not report.can_issue
    assert not report.terminal
    assert "not current" in report.reason


def test_target_synced_but_fleet_not_quorate_is_blocked():
    env = OperatorEnvironment()
    env.sync_target("replica-a")
    report = env.operator.inspect()
    assert report.state is DurableFailoverOperatorState.QUORUM_BLOCKED
    assert not report.can_issue
    assert "quorum" in report.reason


def test_fully_synced_fleet_is_ready():
    env = OperatorEnvironment()
    env.sync_all()
    report = env.operator.inspect()
    assert report.state is DurableFailoverOperatorState.READY
    assert report.can_issue
    assert report.reason == ""
    assert report.replication.promotion_ready
    assert report.fleet is not None
    assert report.fleet.quorum_ready


def test_synchronize_can_make_operator_ready():
    env = OperatorEnvironment()
    result = env.operator.synchronize()
    assert result.before.state is DurableFailoverOperatorState.NEEDS_SYNC
    assert result.after.state is DurableFailoverOperatorState.READY
    assert result.ready
    assert result.target_run.completed
    assert result.fleet_run is not None
    assert result.fleet_run.quorum_ready
    assert result.transferred_items > 0


def test_synchronize_target_only_does_not_create_fleet_quorum():
    env = OperatorEnvironment()
    result = env.operator.synchronize(
        sync_fleet=False
    )
    assert result.target_run.completed
    assert result.fleet_run is None
    assert result.after.state is DurableFailoverOperatorState.QUORUM_BLOCKED
    assert not result.ready


def test_synchronize_honors_explicit_batch_limit():
    env = OperatorEnvironment(count=6)
    result = env.operator.synchronize(
        max_batches=1
    )
    assert not result.ready
    assert not result.target_run.completed


@pytest.mark.parametrize("limit", [0, -1, True, 4097])
def test_synchronize_validates_batch_limit(limit):
    env = OperatorEnvironment()
    with pytest.raises(ValueError, match="max_batches"):
        env.operator.synchronize(
            max_batches=limit
        )


def test_synchronize_validates_sync_fleet_bool():
    env = OperatorEnvironment()
    with pytest.raises(ValueError, match="sync_fleet"):
        env.operator.synchronize(
            sync_fleet="yes"
        )


def test_issue_requires_ready_state():
    env = OperatorEnvironment()
    with pytest.raises(
        DurableFailoverOperatorError,
        match="cannot be issued",
    ):
        env.operator.issue()


def test_issue_returns_signed_ticket_and_report():
    env = OperatorEnvironment()
    env.sync_all()
    result = env.operator.issue(
        ttl_seconds=30
    )
    assert result.ticket.ticket.source_id == "primary"
    assert result.ticket.ticket.target_id == "replica-a"
    assert result.report.ticket_id == result.ticket.ticket.ticket_id
    assert result.report.state is DurableFailoverOperatorState.READY
    assert result.report.can_issue


def test_claim_updates_operator_state():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    report = env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    assert report.state is DurableFailoverOperatorState.CLAIMED
    assert not report.can_issue
    assert not report.terminal
    assert report.failover is not None


def test_complete_updates_operator_state_to_applied():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    report = env.operator.complete(
        issued.ticket,
        consumer_id="operator-1",
    )
    assert report.state is DurableFailoverOperatorState.APPLIED
    assert report.terminal
    assert report.failover.record.phase.value == "applied"


def test_cancel_updates_operator_state_to_cancelled():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    report = env.operator.cancel(
        issued.ticket,
        consumer_id="operator-1",
    )
    assert report.state is DurableFailoverOperatorState.CANCELLED
    assert report.terminal
    assert report.failover.record.phase.value == "cancelled"


def test_inspect_without_ticket_does_not_guess_claim():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    report = env.operator.inspect()
    assert report.state is DurableFailoverOperatorState.READY
    assert report.failover is None


def test_inspect_with_ticket_recovers_claim():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    report = env.operator.inspect(
        ticket_id=issued.ticket.ticket.ticket_id
    )
    assert report.state is DurableFailoverOperatorState.CLAIMED
    assert report.failover is not None


def test_applied_state_can_be_recovered_after_source_advances():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    env.operator.complete(
        issued.ticket,
        consumer_id="operator-1",
    )
    env.advance_source()
    report = env.operator.inspect(
        ticket_id=issued.ticket.ticket.ticket_id
    )
    assert report.state is DurableFailoverOperatorState.APPLIED
    assert report.terminal
    assert not report.replication.promotion_ready


def test_stale_ticket_complete_surfaces_authority_error():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    env.advance_source()
    with pytest.raises(Exception):
        env.operator.complete(
            issued.ticket,
            consumer_id="operator-1",
        )


def test_cancel_stale_claim_remains_available():
    env = OperatorEnvironment()
    env.sync_all()
    issued = env.operator.issue()
    env.operator.claim(
        issued.ticket,
        consumer_id="operator-1",
    )
    env.advance_source()
    report = env.operator.cancel(
        issued.ticket,
        consumer_id="operator-1",
    )
    assert report.state is DurableFailoverOperatorState.CANCELLED


def test_policy_can_allow_nonfleet_operator():
    env = OperatorEnvironment()
    coordinator = DurableFailoverCoordinator(
        env.managers["replica-a"],
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=None,
    )
    operator = DurableFailoverOperator(
        env.managers["replica-a"],
        coordinator,
        fleet=None,
        policy=DurableFailoverOperatorPolicy(
            require_fleet_quorum=False,
        ),
        clock=lambda: env.now[0],
    )
    env.sync_target("replica-a")
    report = operator.inspect()
    assert report.state is DurableFailoverOperatorState.READY
    assert report.can_issue


def test_policy_blocks_nonfleet_operator_by_default():
    env = OperatorEnvironment()
    coordinator = DurableFailoverCoordinator(
        env.managers["replica-a"],
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=None,
    )
    operator = DurableFailoverOperator(
        env.managers["replica-a"],
        coordinator,
        fleet=None,
        clock=lambda: env.now[0],
    )
    env.sync_target("replica-a")
    report = operator.inspect()
    assert report.state is DurableFailoverOperatorState.QUORUM_BLOCKED


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_batches_per_sync": 0},
        {"max_batches_per_sync": 4097},
        {"max_batches_per_sync": True},
        {"require_fleet_quorum": "yes"},
    ],
)
def test_operator_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableFailoverOperatorPolicy(**kwargs)


def test_operator_policy_digest_is_stable():
    first = DurableFailoverOperatorPolicy(
        max_batches_per_sync=4,
    )
    second = DurableFailoverOperatorPolicy(
        max_batches_per_sync=4,
    )
    assert first.digest == second.digest


def test_operator_requires_manager_type():
    env = OperatorEnvironment()
    with pytest.raises(TypeError, match="manager"):
        DurableFailoverOperator(
            object(),
            env.coordinator,
            fleet=env.fleet,
        )


def test_operator_requires_coordinator_type():
    env = OperatorEnvironment()
    with pytest.raises(TypeError, match="coordinator"):
        DurableFailoverOperator(
            env.managers["replica-a"],
            object(),
            fleet=env.fleet,
        )


def test_operator_requires_fleet_type():
    env = OperatorEnvironment()
    with pytest.raises(TypeError, match="fleet"):
        DurableFailoverOperator(
            env.managers["replica-a"],
            env.coordinator,
            fleet=object(),
        )


def test_operator_rejects_manager_coordinator_mismatch():
    env = OperatorEnvironment()
    with pytest.raises(ValueError, match="manager differs"):
        DurableFailoverOperator(
            env.managers["replica-b"],
            env.coordinator,
            fleet=env.fleet,
        )


def test_operator_rejects_fleet_coordinator_mismatch():
    env = OperatorEnvironment()
    coordinator = DurableFailoverCoordinator(
        env.managers["replica-a"],
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=None,
    )
    with pytest.raises(ValueError, match="fleet differs"):
        DurableFailoverOperator(
            env.managers["replica-a"],
            coordinator,
            fleet=env.fleet,
        )


def test_operator_requires_callable_clock():
    env = OperatorEnvironment()
    with pytest.raises(TypeError, match="clock"):
        DurableFailoverOperator(
            env.managers["replica-a"],
            env.coordinator,
            fleet=env.fleet,
            clock=object(),
        )


@pytest.mark.parametrize(
    "value",
    [-1.0, float("inf"), float("nan")],
)
def test_operator_rejects_invalid_clock_value(value):
    env = OperatorEnvironment()
    operator = DurableFailoverOperator(
        env.managers["replica-a"],
        env.coordinator,
        fleet=env.fleet,
        clock=lambda: value,
    )
    with pytest.raises(
        DurableFailoverOperatorError,
        match="clock",
    ):
        operator.inspect()


def test_operator_report_serialization():
    env = OperatorEnvironment()
    env.sync_all()
    report = env.operator.inspect()
    data = report.to_dict()
    assert data["state"] == "ready"
    assert data["can_issue"] is True
    assert data["terminal"] is False
    assert data["digest"] == report.digest
    assert len(report.digest) == 64


def test_sync_result_serialization():
    env = OperatorEnvironment()
    result = env.operator.synchronize()
    data = result.to_dict()
    assert data["ready"] is True
    assert data["transferred_items"] == result.transferred_items
    assert data["digest"] == result.digest


def test_ticket_result_serialization():
    env = OperatorEnvironment()
    env.sync_all()
    result = env.operator.issue()
    data = result.to_dict()
    assert data["ticket"]["ticket"]["ticket_id"] == (
        result.ticket.ticket.ticket_id
    )
    assert data["digest"] == result.digest


def test_operator_state_wire_values_are_stable():
    assert {
        item.value
        for item in DurableFailoverOperatorState
    } == {
        "ready",
        "needs_sync",
        "quorum_blocked",
        "target_blocked",
        "consensus_blocked",
        "history_blocked",
        "claimed",
        "applied",
        "cancelled",
    }


def test_source_growth_moves_ready_operator_back_to_needs_sync():
    env = OperatorEnvironment()
    env.sync_all()
    assert env.operator.inspect().can_issue
    env.advance_source()
    report = env.operator.inspect()
    assert report.state is DurableFailoverOperatorState.NEEDS_SYNC


def test_resynchronization_after_growth_restores_ready_state():
    env = OperatorEnvironment()
    env.sync_all()
    env.advance_source()
    assert not env.operator.inspect().can_issue
    result = env.operator.synchronize()
    assert result.after.state is DurableFailoverOperatorState.READY


def test_operator_report_digest_changes_with_state():
    env = OperatorEnvironment()
    first = env.operator.inspect()
    env.sync_all()
    second = env.operator.inspect()
    assert first.digest != second.digest


def test_operator_report_digest_changes_with_observation_time():
    env = OperatorEnvironment()
    first = env.operator.inspect()
    env.now[0] += 1.0
    second = env.operator.inspect()
    assert first.digest != second.digest
