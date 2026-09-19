"""Fleet-bound durable failover integration tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_failover import (
    DurableFailoverAuthority,
    DurableFailoverCoordinator,
    DurableFailoverPhase,
    DurableFailoverRegistry,
    DurableFailoverTicket,
    DurableFailoverTicketError,
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


class FleetFailoverEnvironment:
    def __init__(self, *, count=2):
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

        self.backends = {}
        self.managers = {}
        self.members = {}
        self.domains = {
            "replica-a": "zone-a",
            "replica-b": "zone-b",
            "replica-c": "zone-c",
        }
        for target_id, domain in self.domains.items():
            backend = InMemoryFencedStore()
            target_journal = DistributedAIDecisionJournal(
                backend,
                namespace="journal",
                clock=lambda: self.now[0],
            )
            target_receipts = DistributedReceiptChain(
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
                    target_journal,
                    policy=replication_policy,
                ),
                DurableChainReplicator(
                    "receipts",
                    self.source_receipts,
                    target_receipts,
                    policy=replication_policy,
                ),
                policy=replication_policy,
            )
            self.backends[target_id] = backend
            self.managers[target_id] = manager
            self.members[target_id] = DurableReplicaFleetMember(
                target_id,
                domain,
                manager,
            )

        self.fleet_policy = DurableReplicaFleetPolicy(
            min_ready_replicas=2,
            min_ready_failure_domains=2,
        )
        self.fleet = DurableReplicaFleet(
            "primary",
            tuple(self.members.values()),
            policy=self.fleet_policy,
            clock=lambda: self.now[0],
        )
        self.registry = DurableFailoverRegistry(
            InMemoryFencedStore(),
            namespace="failover",
            clock=lambda: self.now[0],
        )
        self.signer = ArtifactSigner(
            "fleet-failover",
            b"k" * 32,
            clock=lambda: self.now[0],
        )
        self.authority = DurableFailoverAuthority(
            self.signer,
            clock=lambda: self.now[0],
            nonce_factory=lambda: "fleet-nonce",
        )

    def sync(self, *targets):
        for target in targets:
            self.managers[target].sync()

    def sync_all(self):
        self.fleet.sync_all()

    def coordinator(
        self,
        target="replica-a",
        *,
        fleet=True,
    ):
        return DurableFailoverCoordinator(
            self.managers[target],
            self.authority,
            self.registry,
            source_id="primary",
            target_id=target,
            fleet=self.fleet if fleet else None,
        )

    def advance_source(self):
        index = self.source_journal.length() + 1
        self.source_journal.append(
            f"event.{index}",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
        )
        self.source_receipts.append(receipt(index))


def test_fleet_ticket_binds_state_and_policy():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    fleet_report = env.fleet.require_quorum(
        target_id="replica-a"
    )
    signed = env.coordinator().issue()
    assert (
        signed.ticket.fleet_state_digest
        == fleet_report.state_digest
    )
    assert (
        signed.ticket.fleet_policy_digest
        == fleet_report.policy_digest
    )


def test_fleet_issue_requires_quorum():
    env = FleetFailoverEnvironment()
    env.sync("replica-a")
    with pytest.raises(
        DurableFailoverTicketError,
        match="fleet quorum",
    ):
        env.coordinator().issue()


def test_fleet_issue_requires_requested_target_ready():
    env = FleetFailoverEnvironment()
    env.sync("replica-b", "replica-c")
    assert env.fleet.inspect().quorum_ready
    with pytest.raises(
        DurableFailoverTicketError,
        match="fleet quorum",
    ):
        env.coordinator(
            target="replica-a"
        ).issue()


def test_fleet_issue_succeeds_with_two_domain_quorum():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    signed = env.coordinator().issue()
    assert signed.ticket.fleet_state_digest
    assert signed.ticket.fleet_policy_digest


def test_monitoring_time_change_does_not_stale_fleet_ticket():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    coordinator = env.coordinator()
    signed = coordinator.issue()
    before = env.fleet.inspect()
    env.now[0] += 1.0
    after = env.fleet.inspect()
    assert before.digest != after.digest
    assert before.state_digest == after.state_digest
    claim = coordinator.claim(
        signed,
        consumer_id="operator",
    )
    assert claim.record.phase is DurableFailoverPhase.CLAIMED


def test_newly_ready_replica_stales_existing_fleet_ticket():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    coordinator = env.coordinator()
    signed = coordinator.issue()
    env.sync("replica-c")
    assert env.fleet.inspect().quorum_ready
    with pytest.raises(
        DurableFailoverTicketError,
        match="fleet state differs",
    ):
        coordinator.claim(
            signed,
            consumer_id="operator",
        )


def test_source_growth_stales_fleet_ticket_even_after_partial_quorum_resync():
    env = FleetFailoverEnvironment()
    env.sync_all()
    coordinator = env.coordinator()
    signed = coordinator.issue()
    env.advance_source()
    env.sync("replica-a", "replica-b")
    assert env.fleet.inspect().quorum_ready
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        coordinator.claim(
            signed,
            consumer_id="operator",
        )


def test_fleet_quorum_loss_between_claim_and_complete_blocks_apply():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    coordinator = env.coordinator()
    signed = coordinator.issue()
    coordinator.claim(
        signed,
        consumer_id="operator",
    )
    env.advance_source()
    env.sync("replica-a")
    assert not env.fleet.inspect().quorum_ready
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        coordinator.complete(
            signed,
            consumer_id="operator",
        )
    current = env.registry.current(
        signed.ticket.ticket_id
    )
    assert current.record.phase is DurableFailoverPhase.CLAIMED


def test_restoring_quorum_with_new_roots_still_requires_new_ticket():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    coordinator = env.coordinator()
    signed = coordinator.issue()
    coordinator.claim(
        signed,
        consumer_id="operator",
    )
    env.advance_source()
    env.sync("replica-a", "replica-b")
    assert env.fleet.inspect().quorum_ready
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        coordinator.complete(
            signed,
            consumer_id="operator",
        )


def test_fleet_claim_and_complete_happy_path():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    coordinator = env.coordinator()
    signed = coordinator.issue()
    claimed = coordinator.claim(
        signed,
        consumer_id="operator",
    )
    assert claimed.record.phase is DurableFailoverPhase.CLAIMED
    applied = coordinator.complete(
        signed,
        consumer_id="operator",
    )
    assert applied.record.phase is DurableFailoverPhase.APPLIED


def test_applied_fleet_failover_retry_survives_later_quorum_loss():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    coordinator = env.coordinator()
    signed = coordinator.issue()
    coordinator.claim(
        signed,
        consumer_id="operator",
    )
    applied = coordinator.complete(
        signed,
        consumer_id="operator",
    )
    env.advance_source()
    assert not env.fleet.inspect().quorum_ready
    retried = coordinator.complete(
        signed,
        consumer_id="operator",
    )
    assert retried == applied


def test_fleet_claim_can_be_cancelled_after_quorum_loss():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    coordinator = env.coordinator()
    signed = coordinator.issue()
    coordinator.claim(
        signed,
        consumer_id="operator",
    )
    env.advance_source()
    cancelled = coordinator.cancel(
        signed,
        consumer_id="operator",
    )
    assert cancelled.record.phase is DurableFailoverPhase.CANCELLED


def test_nonfleet_ticket_is_rejected_by_fleet_coordinator():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    nonfleet = env.coordinator(
        fleet=False
    )
    signed = nonfleet.issue()
    assert not signed.ticket.fleet_state_digest
    with pytest.raises(
        DurableFailoverTicketError,
        match="lacks fleet commitments",
    ):
        env.coordinator().claim(
            signed,
            consumer_id="operator",
        )


def test_fleet_ticket_is_rejected_by_nonfleet_coordinator():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    signed = env.coordinator().issue()
    with pytest.raises(
        DurableFailoverTicketError,
        match="requires unavailable fleet",
    ):
        env.coordinator(
            fleet=False
        ).claim(
            signed,
            consumer_id="operator",
        )


def test_authority_can_issue_explicit_fleet_commitments():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    report = env.fleet.inspect()
    signed = env.authority.issue(
        env.managers["replica-a"],
        source_id="primary",
        target_id="replica-a",
        fleet_state_digest=report.state_digest,
        fleet_policy_digest=report.policy_digest,
    )
    assert (
        signed.ticket.fleet_state_digest
        == report.state_digest
    )


def test_authority_rejects_unpaired_fleet_commitments():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    with pytest.raises(
        ValueError,
        match="paired",
    ):
        env.authority.issue(
            env.managers["replica-a"],
            source_id="primary",
            target_id="replica-a",
            fleet_state_digest=fp("a"),
        )


def test_ticket_rejects_unpaired_fleet_digests():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    signed = env.coordinator().issue()
    with pytest.raises(
        ValueError,
        match="configured together",
    ):
        DurableFailoverTicket(
            signed.ticket.schema_version,
            signed.ticket.ticket_id,
            signed.ticket.source_id,
            signed.ticket.target_id,
            signed.ticket.issued_at,
            signed.ticket.expires_at,
            signed.ticket.nonce,
            signed.ticket.replication_report_digest,
            signed.ticket.policy_digest,
            signed.ticket.journal_sequence,
            signed.ticket.journal_root,
            signed.ticket.receipt_sequence,
            signed.ticket.receipt_root,
            fp("a"),
            "",
        )


def test_fleet_policy_change_invalidates_ticket():
    env = FleetFailoverEnvironment()
    env.sync_all()
    signed = env.coordinator().issue()

    changed_fleet = DurableReplicaFleet(
        "primary",
        tuple(env.members.values()),
        policy=DurableReplicaFleetPolicy(
            min_ready_replicas=1,
            min_ready_failure_domains=1,
        ),
        clock=lambda: env.now[0],
    )
    changed = DurableFailoverCoordinator(
        env.managers["replica-a"],
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=changed_fleet,
    )
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        changed.claim(
            signed,
            consumer_id="operator",
        )


def test_fleet_state_digest_is_time_independent():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    first = env.fleet.inspect()
    env.now[0] += 100.0
    second = env.fleet.inspect()
    assert first.state_digest == second.state_digest
    assert first.digest != second.digest


def test_fleet_state_digest_changes_when_ready_members_change():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    first = env.fleet.inspect()
    env.sync("replica-c")
    second = env.fleet.inspect()
    assert first.state_digest != second.state_digest


def test_fleet_state_digest_changes_when_replication_roots_change():
    env = FleetFailoverEnvironment()
    env.sync_all()
    first = env.fleet.inspect()
    env.advance_source()
    env.sync_all()
    second = env.fleet.inspect()
    assert first.state_digest != second.state_digest


def test_coordinator_rejects_wrong_fleet_source():
    env = FleetFailoverEnvironment()
    wrong = DurableReplicaFleet(
        "other-primary",
        tuple(env.members.values()),
        policy=env.fleet_policy,
        clock=lambda: env.now[0],
    )
    with pytest.raises(
        ValueError,
        match="source_id mismatch",
    ):
        DurableFailoverCoordinator(
            env.managers["replica-a"],
            env.authority,
            env.registry,
            source_id="primary",
            target_id="replica-a",
            fleet=wrong,
        )


def test_coordinator_rejects_wrong_fleet_type():
    env = FleetFailoverEnvironment()
    with pytest.raises(
        TypeError,
        match="fleet",
    ):
        DurableFailoverCoordinator(
            env.managers["replica-a"],
            env.authority,
            env.registry,
            source_id="primary",
            target_id="replica-a",
            fleet=object(),
        )


def test_ticket_id_changes_when_fleet_state_changes():
    base = dict(
        source_id="primary",
        target_id="replica",
        issued_at=1.0,
        expires_at=2.0,
        nonce="nonce",
        replication_report_digest=fp("a"),
        journal_root=fp("b"),
        receipt_root=fp("c"),
        fleet_policy_digest=fp("d"),
    )
    first = DurableFailoverTicket.derive_id(
        **base,
        fleet_state_digest=fp("e"),
    )
    second = DurableFailoverTicket.derive_id(
        **base,
        fleet_state_digest=fp("f"),
    )
    assert first != second


def test_ticket_id_changes_when_fleet_policy_changes():
    base = dict(
        source_id="primary",
        target_id="replica",
        issued_at=1.0,
        expires_at=2.0,
        nonce="nonce",
        replication_report_digest=fp("a"),
        journal_root=fp("b"),
        receipt_root=fp("c"),
        fleet_state_digest=fp("e"),
    )
    first = DurableFailoverTicket.derive_id(
        **base,
        fleet_policy_digest=fp("d"),
    )
    second = DurableFailoverTicket.derive_id(
        **base,
        fleet_policy_digest=fp("f"),
    )
    assert first != second


def test_fleet_ticket_serialization_exposes_commitments():
    env = FleetFailoverEnvironment()
    env.sync("replica-a", "replica-b")
    signed = env.coordinator().issue()
    data = signed.to_dict()
    assert (
        data["ticket"]["fleet_state_digest"]
        == signed.ticket.fleet_state_digest
    )
    assert (
        data["ticket"]["fleet_policy_digest"]
        == signed.ticket.fleet_policy_digest
    )
