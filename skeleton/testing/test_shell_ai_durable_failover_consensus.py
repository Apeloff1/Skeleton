"""End-to-end failover tests for replica consensus and monotonic history."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_failover import (
    DurableFailoverAuthority,
    DurableFailoverCoordinator,
    DurableFailoverRegistry,
    DurableFailoverTicketError,
)
from skeleton.shells.ai.durable_failover_operator import (
    DurableFailoverOperator,
    DurableFailoverOperatorReport,
    DurableFailoverOperatorState,
)
from skeleton.shells.ai.durable_replica_consensus import (
    DurableReplicaConsensusEvaluator,
    DurableReplicaConsensusPolicy,
)
from skeleton.shells.ai.durable_replica_consensus_history import (
    DurableReplicaConsensusHistoryError,
    DurableReplicaConsensusHistoryStore,
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


class Source:
    def __init__(self, *, count=3, now=None):
        self.now = now or [100.0]
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            clock=lambda: self.now[0],
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
        )
        self.count = 0
        for _ in range(count):
            self.advance()

    def advance(self):
        self.count += 1
        index = self.count
        self.journal.append(
            f"event.{index}",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
        )
        self.receipts.append(receipt(index))


class Replica:
    def __init__(
        self,
        target_id,
        domain,
        source: Source,
        *,
        policy=None,
        required=False,
    ):
        self.target_id = target_id
        self.domain = domain
        self.source = source
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            clock=lambda: source.now[0],
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
        )
        self.policy = policy or DurableReplicationPolicy(
            max_batch_items=2,
            max_batches_per_run=32,
        )
        self.manager = DurableEvidenceReplicaManager(
            DurableChainReplicator(
                "journal",
                source.journal,
                self.journal,
                policy=self.policy,
            ),
            DurableChainReplicator(
                "receipts",
                source.receipts,
                self.receipts,
                policy=self.policy,
            ),
            policy=self.policy,
        )
        self.member = DurableReplicaFleetMember(
            target_id,
            domain,
            self.manager,
            required=required,
        )

    def sync(self):
        return self.manager.sync()


class ConsensusFailoverEnvironment:
    def __init__(
        self,
        *,
        count=3,
        sync=True,
        strict_history=True,
        required_target="",
    ):
        self.now = [100.0]
        self.source = Source(
            count=count,
            now=self.now,
        )
        self.replicas = {
            "replica-a": Replica(
                "replica-a",
                "zone-a",
                self.source,
                required=(
                    required_target
                    == "replica-a"
                ),
            ),
            "replica-b": Replica(
                "replica-b",
                "zone-b",
                self.source,
                required=(
                    required_target
                    == "replica-b"
                ),
            ),
            "replica-c": Replica(
                "replica-c",
                "zone-c",
                self.source,
                required=(
                    required_target
                    == "replica-c"
                ),
            ),
        }
        self.fleet_policy = DurableReplicaFleetPolicy(
            min_ready_replicas=2,
            min_ready_failure_domains=2,
        )
        self.fleet = DurableReplicaFleet(
            "primary",
            tuple(
                replica.member
                for replica in self.replicas.values()
            ),
            policy=self.fleet_policy,
            clock=lambda: self.now[0],
        )
        if sync:
            self.fleet.sync_all()

        self.consensus = DurableReplicaConsensusEvaluator(
            DurableReplicaConsensusPolicy(
                min_agreeing_replicas=2,
                min_agreeing_failure_domains=2,
                min_agreement_fraction=2.0 / 3.0,
                require_fleet_quorum=True,
                require_all_required_members=True,
            )
        )
        self.registry_backend = InMemoryFencedStore(
            clock=lambda: self.now[0],
        )
        self.history = (
            DurableReplicaConsensusHistoryStore(
                self.registry_backend,
                namespace="consensus-history",
                clock=lambda: self.now[0],
            )
            if strict_history
            else None
        )
        self.signer = ArtifactSigner(
            "failover-key",
            b"k" * 32,
            clock=lambda: self.now[0],
        )
        self.authority = DurableFailoverAuthority(
            self.signer,
            max_ttl_seconds=300.0,
            max_clock_skew_seconds=5.0,
            clock=lambda: self.now[0],
            nonce_factory=lambda: (
                f"nonce-{self.now[0]}"
            ),
        )
        self.registry = DurableFailoverRegistry(
            self.registry_backend,
            namespace="failover",
            clock=lambda: self.now[0],
        )
        self.target = self.replicas[
            "replica-a"
        ]
        self.coordinator = DurableFailoverCoordinator(
            self.target.manager,
            self.authority,
            self.registry,
            source_id="primary",
            target_id="replica-a",
            fleet=self.fleet,
            consensus=self.consensus,
            consensus_history=self.history,
        )

    def issue(self, **kwargs):
        return self.coordinator.issue(
            **kwargs
        )

    def claim(
        self,
        signed,
        *,
        consumer_id="operator",
    ):
        return self.coordinator.claim(
            signed,
            consumer_id=consumer_id,
        )

    def complete(
        self,
        signed,
        *,
        consumer_id="operator",
    ):
        return self.coordinator.complete(
            signed,
            consumer_id=consumer_id,
        )

    def grow_and_sync(self):
        self.now[0] += 1
        self.source.advance()
        return self.fleet.sync_all()


def test_consensus_enabled_issue_binds_consensus_digests():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    ticket = signed.ticket
    report = env.coordinator.consensus_report()
    assert report is not None
    assert report.certifiable
    assert (
        ticket.consensus_state_digest
        == report.state_digest
    )
    assert (
        ticket.consensus_policy_digest
        == report.consensus_policy_digest
    )
    assert (
        ticket.fleet_state_digest
        == report.fleet_state_digest
    )
    assert (
        ticket.journal_root
        == report.selected.head.journal_root
    )
    assert (
        ticket.receipt_root
        == report.selected.head.receipt_root
    )


def test_issue_records_initial_consensus_history_epoch():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    current = env.history.current(
        "primary"
    )
    assert current is not None
    assert current.epoch.generation == 1
    assert (
        current.epoch.consensus_state_digest
        == signed.ticket.consensus_state_digest
    )
    assert (
        current.epoch.journal_root
        == signed.ticket.journal_root
    )
    assert (
        current.epoch.receipt_root
        == signed.ticket.receipt_root
    )


def test_claim_requires_current_consensus_history():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    claimed = env.claim(signed)
    assert claimed.record.ticket_id == (
        signed.ticket.ticket_id
    )
    assert claimed.record.consumer_id == "operator"


def test_complete_requires_current_consensus_history():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    env.claim(signed)
    applied = env.complete(signed)
    assert applied.record.phase.value == "applied"


def test_full_consensus_failover_happy_path():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    claimed = env.claim(signed)
    applied = env.complete(signed)
    assert (
        claimed.record.claim_id
        == applied.record.claim_id
    )
    assert (
        applied.record.applied_report_digest
        == env.target.manager.inspect().digest
    )
    assert env.history.verify(
        "primary",
        journal_chain=env.source.journal,
        receipt_chain=env.source.receipts,
    )


def test_source_growth_makes_old_consensus_ticket_stale():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    env.grow_and_sync()
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        env.claim(signed)


def test_new_issue_after_growth_advances_consensus_history():
    env = ConsensusFailoverEnvironment()
    first = env.issue()
    first_epoch = env.history.current(
        "primary"
    ).epoch
    env.grow_and_sync()
    second = env.issue()
    second_epoch = env.history.current(
        "primary"
    ).epoch
    assert second_epoch.generation == 2
    assert (
        second_epoch.previous_digest
        == first_epoch.digest
    )
    assert (
        second.ticket.journal_sequence
        > first.ticket.journal_sequence
    )
    assert (
        second.ticket.receipt_sequence
        > first.ticket.receipt_sequence
    )


def test_claim_new_generation_after_growth_succeeds():
    env = ConsensusFailoverEnvironment()
    env.issue()
    env.grow_and_sync()
    current = env.issue()
    claimed = env.claim(current)
    assert claimed.record.ticket_id == (
        current.ticket.ticket_id
    )


def test_history_remains_verified_across_multiple_generations():
    env = ConsensusFailoverEnvironment()
    env.issue()
    for _ in range(4):
        env.grow_and_sync()
        env.issue()
    lineage = env.history.lineage(
        "primary"
    )
    assert tuple(
        epoch.generation
        for epoch in lineage
    ) == (1, 2, 3, 4, 5)
    assert env.history.verify(
        "primary",
        journal_chain=env.source.journal,
        receipt_chain=env.source.receipts,
    )


def test_unsynchronized_fleet_blocks_consensus_issue():
    env = ConsensusFailoverEnvironment(
        sync=False
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="fleet quorum",
    ):
        env.issue()


def test_single_ready_replica_does_not_meet_consensus():
    env = ConsensusFailoverEnvironment(
        sync=False
    )
    env.replicas["replica-a"].sync()
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        env.issue()


def test_two_ready_replicas_in_distinct_domains_can_issue():
    env = ConsensusFailoverEnvironment(
        sync=False
    )
    env.replicas["replica-a"].sync()
    env.replicas["replica-b"].sync()
    signed = env.issue()
    assert signed.ticket.consensus_state_digest


def test_split_brain_member_blocks_strict_consensus_issue():
    env = ConsensusFailoverEnvironment()
    rogue = Source(
        count=3,
        now=env.now,
    )
    rogue.advance()
    divergent = Replica(
        "replica-c",
        "zone-c",
        rogue,
    )
    divergent.sync()
    env.replicas["replica-c"] = divergent
    env.fleet = DurableReplicaFleet(
        "primary",
        (
            env.replicas["replica-a"].member,
            env.replicas["replica-b"].member,
            divergent.member,
        ),
        policy=env.fleet_policy,
        clock=lambda: env.now[0],
    )
    env.coordinator.fleet = env.fleet
    with pytest.raises(
        DurableFailoverTicketError,
        match="consensus",
    ):
        env.issue()


def test_split_brain_is_visible_in_consensus_report():
    env = ConsensusFailoverEnvironment()
    rogue = Source(
        count=4,
        now=env.now,
    )
    divergent = Replica(
        "replica-c",
        "zone-c",
        rogue,
    )
    divergent.sync()
    env.fleet = DurableReplicaFleet(
        "primary",
        (
            env.replicas["replica-a"].member,
            env.replicas["replica-b"].member,
            divergent.member,
        ),
        policy=env.fleet_policy,
        clock=lambda: env.now[0],
    )
    env.coordinator.fleet = env.fleet
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        env.coordinator.consensus_report()


def test_required_dissenting_member_blocks_issue():
    env = ConsensusFailoverEnvironment(
        required_target="replica-c"
    )
    rogue = Source(
        count=4,
        now=env.now,
    )
    divergent = Replica(
        "replica-c",
        "zone-c",
        rogue,
        required=True,
    )
    divergent.sync()
    env.fleet = DurableReplicaFleet(
        "primary",
        (
            env.replicas["replica-a"].member,
            env.replicas["replica-b"].member,
            divergent.member,
        ),
        policy=env.fleet_policy,
        clock=lambda: env.now[0],
    )
    env.coordinator.fleet = env.fleet
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        env.issue()


def test_consensus_requires_fleet_in_coordinator():
    env = ConsensusFailoverEnvironment()
    with pytest.raises(
        ValueError,
        match="requires a failover fleet",
    ):
        DurableFailoverCoordinator(
            env.target.manager,
            env.authority,
            env.registry,
            source_id="primary",
            target_id="replica-a",
            consensus=env.consensus,
        )


def test_consensus_history_requires_consensus():
    env = ConsensusFailoverEnvironment()
    with pytest.raises(
        ValueError,
        match="history requires replica consensus",
    ):
        DurableFailoverCoordinator(
            env.target.manager,
            env.authority,
            env.registry,
            source_id="primary",
            target_id="replica-a",
            fleet=env.fleet,
            consensus_history=env.history,
        )


def test_consensus_type_validation():
    env = ConsensusFailoverEnvironment()
    with pytest.raises(
        TypeError,
        match="consensus must",
    ):
        DurableFailoverCoordinator(
            env.target.manager,
            env.authority,
            env.registry,
            source_id="primary",
            target_id="replica-a",
            fleet=env.fleet,
            consensus=object(),
        )


def test_consensus_history_type_validation():
    env = ConsensusFailoverEnvironment()
    with pytest.raises(
        TypeError,
        match="consensus_history",
    ):
        DurableFailoverCoordinator(
            env.target.manager,
            env.authority,
            env.registry,
            source_id="primary",
            target_id="replica-a",
            fleet=env.fleet,
            consensus=env.consensus,
            consensus_history=object(),
        )


def test_legacy_failover_without_consensus_remains_compatible():
    env = ConsensusFailoverEnvironment(
        strict_history=False
    )
    coordinator = DurableFailoverCoordinator(
        env.target.manager,
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=env.fleet,
    )
    signed = coordinator.issue()
    assert signed.ticket.consensus_state_digest == ""
    assert signed.ticket.consensus_policy_digest == ""
    coordinator.claim(
        signed,
        consumer_id="legacy",
    )
    applied = coordinator.complete(
        signed,
        consumer_id="legacy",
    )
    assert applied.record.phase.value == "applied"


def test_consensus_ticket_cannot_be_claimed_without_consensus_verifier():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    legacy = DurableFailoverCoordinator(
        env.target.manager,
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=env.fleet,
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="unavailable replica consensus",
    ):
        legacy.claim(
            signed,
            consumer_id="legacy",
        )


def test_authority_direct_issue_accepts_consensus_commitments():
    env = ConsensusFailoverEnvironment()
    fleet_report = env.fleet.require_quorum(
        target_id="replica-a"
    )
    consensus = env.consensus.require_consensus(
        fleet_report,
        target_id="replica-a",
    )
    signed = env.authority.issue(
        env.target.manager,
        source_id="primary",
        target_id="replica-a",
        fleet_state_digest=(
            fleet_report.state_digest
        ),
        fleet_policy_digest=(
            fleet_report.policy_digest
        ),
        consensus_state_digest=(
            consensus.state_digest
        ),
        consensus_policy_digest=(
            consensus.consensus_policy_digest
        ),
    )
    assert (
        signed.ticket.consensus_state_digest
        == consensus.state_digest
    )


def test_authority_rejects_unpaired_consensus_commitments():
    env = ConsensusFailoverEnvironment()
    fleet_report = env.fleet.require_quorum()
    with pytest.raises(
        ValueError,
        match="must be paired",
    ):
        env.authority.issue(
            env.target.manager,
            source_id="primary",
            target_id="replica-a",
            fleet_state_digest=(
                fleet_report.state_digest
            ),
            fleet_policy_digest=(
                fleet_report.policy_digest
            ),
            consensus_state_digest=fp("c"),
        )


def test_authority_rejects_consensus_without_fleet_commitments():
    env = ConsensusFailoverEnvironment()
    with pytest.raises(
        ValueError,
        match="require fleet",
    ):
        env.authority.issue(
            env.target.manager,
            source_id="primary",
            target_id="replica-a",
            consensus_state_digest=fp("c"),
            consensus_policy_digest=fp("p"),
        )


def test_failover_ticket_id_changes_when_consensus_changes():
    env = ConsensusFailoverEnvironment()
    fleet_report = env.fleet.require_quorum()
    first = env.authority.issue(
        env.target.manager,
        source_id="primary",
        target_id="replica-a",
        fleet_state_digest=(
            fleet_report.state_digest
        ),
        fleet_policy_digest=(
            fleet_report.policy_digest
        ),
        consensus_state_digest=fp("c"),
        consensus_policy_digest=fp("p"),
    )
    second = env.authority.issue(
        env.target.manager,
        source_id="primary",
        target_id="replica-a",
        fleet_state_digest=(
            fleet_report.state_digest
        ),
        fleet_policy_digest=(
            fleet_report.policy_digest
        ),
        consensus_state_digest=fp("d"),
        consensus_policy_digest=fp("p"),
    )
    assert (
        first.ticket.ticket_id
        != second.ticket.ticket_id
    )


def test_static_ticket_verification_checks_consensus_metadata():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    metadata = dict(
        signed.signature.metadata
    )
    metadata["consensus_state_digest"] = fp("9")
    from skeleton.shells.ai.signed_artifact import SignedArtifact
    from skeleton.shells.ai.durable_failover import SignedDurableFailoverTicket

    forged = SignedDurableFailoverTicket(
        signed.ticket,
        SignedArtifact(
            signed.signature.artifact_type,
            signed.signature.artifact_digest,
            signed.signature.signer_id,
            signed.signature.issued_at,
            signed.signature.signature,
            metadata,
        ),
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="metadata",
    ):
        env.authority.verify_static(
            forged
        )


def test_history_corruption_blocks_new_issue():
    env = ConsensusFailoverEnvironment()
    first = env.issue()
    current = env.history.current(
        "primary"
    )
    key = env.history._epoch_key(
        current.epoch.digest
    )
    record = env.registry_backend.get(
        env.history.namespace,
        key,
    )
    env.registry_backend.compare_and_swap(
        env.history.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            current.epoch,
            fleet_state_digest=fp("9"),
        ),
    )
    env.grow_and_sync()
    with pytest.raises(
        DurableFailoverTicketError,
        match="history",
    ):
        env.issue()
    assert first.ticket.ticket_id


def test_missing_history_epoch_blocks_claim():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    current = env.history.current(
        "primary"
    )
    key = env.history._epoch_key(
        current.epoch.digest
    )
    record = env.registry_backend.get(
        env.history.namespace,
        key,
    )
    env.registry_backend.delete(
        env.history.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        (DurableFailoverTicketError, DurableReplicaConsensusHistoryError),
    ):
        env.claim(signed)


def test_history_head_tamper_blocks_complete():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    env.claim(signed)
    head_key = env.history._source_key(
        "primary"
    )
    record = env.registry_backend.get(
        env.history.namespace,
        head_key,
    )
    env.registry_backend.compare_and_swap(
        env.history.namespace,
        head_key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            generation=record.value.generation + 1,
        ),
    )
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        env.complete(signed)


def test_consensus_history_current_is_exposed():
    env = ConsensusFailoverEnvironment()
    assert (
        env.coordinator
        .consensus_history_current()
        is None
    )
    env.issue()
    current = (
        env.coordinator
        .consensus_history_current()
    )
    assert current is not None
    assert current.epoch.generation == 1


def test_no_history_configuration_returns_none():
    env = ConsensusFailoverEnvironment(
        strict_history=False
    )
    coordinator = DurableFailoverCoordinator(
        env.target.manager,
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=env.fleet,
        consensus=env.consensus,
    )
    assert (
        coordinator.consensus_history_current()
        is None
    )
    signed = coordinator.issue()
    assert signed.ticket.consensus_state_digest


def test_target_not_in_consensus_quorum_blocks_issue():
    env = ConsensusFailoverEnvironment()
    # Replace target-A's manager with a divergent source while B/C remain
    # canonical. Strict consensus sees a split and blocks before ticket issue.
    rogue = Source(
        count=4,
        now=env.now,
    )
    divergent_a = Replica(
        "replica-a",
        "zone-a",
        rogue,
    )
    divergent_a.sync()
    env.replicas["replica-a"] = divergent_a
    env.fleet = DurableReplicaFleet(
        "primary",
        (
            divergent_a.member,
            env.replicas["replica-b"].member,
            env.replicas["replica-c"].member,
        ),
        policy=env.fleet_policy,
        clock=lambda: env.now[0],
    )
    env.coordinator = DurableFailoverCoordinator(
        divergent_a.manager,
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=env.fleet,
        consensus=env.consensus,
        consensus_history=env.history,
    )
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        env.issue()


def test_ticket_serialization_contains_consensus_commitments():
    env = ConsensusFailoverEnvironment()
    ticket = env.issue().ticket
    data = ticket.to_dict()
    assert (
        data["consensus_state_digest"]
        == ticket.consensus_state_digest
    )
    assert (
        data["consensus_policy_digest"]
        == ticket.consensus_policy_digest
    )


def test_consensus_history_records_exact_agreeing_targets():
    env = ConsensusFailoverEnvironment()
    env.issue()
    current = env.history.current(
        "primary"
    )
    assert current.epoch.agreeing_targets == (
        "replica-a",
        "replica-b",
        "replica-c",
    )
    assert (
        current.epoch.agreeing_failure_domains
        == ("zone-a", "zone-b", "zone-c")
    )


def test_history_records_policy_only_change_as_new_generation():
    env = ConsensusFailoverEnvironment()
    env.issue()
    first = env.history.current(
        "primary"
    ).epoch
    env.consensus = DurableReplicaConsensusEvaluator(
        DurableReplicaConsensusPolicy(
            min_agreeing_replicas=2,
            min_agreeing_failure_domains=2,
            min_agreement_fraction=0.9,
        )
    )
    env.coordinator.consensus = env.consensus
    env.now[0] += 1
    env.issue()
    second = env.history.current(
        "primary"
    ).epoch
    assert second.generation == 2
    assert (
        second.journal_root
        == first.journal_root
    )
    assert (
        second.consensus_policy_digest
        != first.consensus_policy_digest
    )


def test_old_ticket_rejected_after_consensus_policy_change():
    env = ConsensusFailoverEnvironment()
    old = env.issue()
    env.consensus = DurableReplicaConsensusEvaluator(
        DurableReplicaConsensusPolicy(
            min_agreeing_replicas=2,
            min_agreeing_failure_domains=2,
            min_agreement_fraction=0.9,
        )
    )
    env.coordinator.consensus = env.consensus
    with pytest.raises(
        DurableFailoverTicketError,
    ):
        env.claim(old)


def test_cancel_remains_available_after_consensus_drift():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    env.claim(signed)
    env.grow_and_sync()
    cancelled = env.coordinator.cancel(
        signed,
        consumer_id="operator",
    )
    assert cancelled.record.phase.value == "cancelled"


def test_applied_idempotent_complete_survives_later_consensus_growth():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    env.claim(signed)
    applied = env.complete(signed)
    env.grow_and_sync()
    again = env.complete(signed)
    assert again == applied


def test_history_is_not_mutated_by_claim():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    before = env.history.current(
        "primary"
    )
    env.claim(signed)
    after = env.history.current(
        "primary"
    )
    assert after == before


def test_history_is_not_mutated_by_complete():
    env = ConsensusFailoverEnvironment()
    signed = env.issue()
    env.claim(signed)
    before = env.history.current(
        "primary"
    )
    env.complete(signed)
    after = env.history.current(
        "primary"
    )
    assert after == before


def test_reissue_same_consensus_is_history_idempotent():
    env = ConsensusFailoverEnvironment()
    first = env.issue()
    first_history = env.history.current(
        "primary"
    )
    second = env.issue()
    second_history = env.history.current(
        "primary"
    )
    assert (
        second_history
        == first_history
    )
    # Nonce incorporates same time in fixture, so identical issue inputs are
    # deterministic here and return the same ticket identity.
    assert (
        first.ticket.ticket_id
        == second.ticket.ticket_id
    )


def test_consensus_report_public_helper_returns_live_state():
    env = ConsensusFailoverEnvironment()
    report = env.coordinator.consensus_report()
    assert report is not None
    assert report.certifiable
    assert (
        report.selected.head.journal_root
        == env.source.journal.root_hash()
    )
    assert (
        report.selected.head.receipt_root
        == env.source.receipts.root_hash()
    )

def make_operator(env: ConsensusFailoverEnvironment):
    return DurableFailoverOperator(
        env.target.manager,
        env.coordinator,
        fleet=env.fleet,
        clock=lambda: env.now[0],
    )


def test_operator_reports_live_consensus_before_first_issue():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    report = operator.inspect()
    assert report.state is DurableFailoverOperatorState.READY
    assert report.can_issue
    assert report.consensus is not None
    assert report.consensus.certifiable
    assert report.consensus_history is None


def test_operator_issue_records_and_surfaces_consensus_history():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    issued = operator.issue()
    assert issued.report.state is DurableFailoverOperatorState.READY
    assert issued.report.consensus is not None
    assert issued.report.consensus_history is not None
    assert issued.report.consensus_history.epoch.generation == 1
    assert (
        issued.report.consensus_history.epoch.consensus_state_digest
        == issued.ticket.ticket.consensus_state_digest
    )


def test_operator_surfaces_history_block_after_source_growth_and_resync():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    operator.issue()
    env.grow_and_sync()
    report = operator.inspect()
    assert report.state is DurableFailoverOperatorState.HISTORY_BLOCKED
    assert not report.can_issue
    assert report.consensus is not None
    assert report.consensus_history is None
    assert "history" in report.reason.lower()


def test_operator_issue_advances_history_after_explicit_history_block():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    first = operator.issue()
    env.grow_and_sync()
    blocked = operator.inspect()
    assert blocked.state is DurableFailoverOperatorState.HISTORY_BLOCKED

    # The operator intentionally refuses issue while history is stale. The
    # coordinator issue path is the authority that may advance consensus
    # history after re-validating the live roots.
    second_ticket = env.coordinator.issue()
    refreshed = operator.inspect(
        ticket_id=second_ticket.ticket.ticket_id
    )
    assert refreshed.state is DurableFailoverOperatorState.READY
    assert refreshed.consensus_history is not None
    assert refreshed.consensus_history.epoch.generation == 2
    assert (
        first.ticket.ticket.journal_root
        != second_ticket.ticket.journal_root
    )


def test_operator_surfaces_consensus_block_for_split_brain():
    env = ConsensusFailoverEnvironment()
    rogue = Source(
        count=4,
        now=env.now,
    )
    divergent = Replica(
        "replica-c",
        "zone-c",
        rogue,
    )
    divergent.sync()
    env.fleet = DurableReplicaFleet(
        "primary",
        (
            env.replicas["replica-a"].member,
            env.replicas["replica-b"].member,
            divergent.member,
        ),
        policy=env.fleet_policy,
        clock=lambda: env.now[0],
    )
    env.coordinator.fleet = env.fleet
    operator = DurableFailoverOperator(
        env.target.manager,
        env.coordinator,
        fleet=env.fleet,
        clock=lambda: env.now[0],
    )
    report = operator.inspect()
    assert report.state is DurableFailoverOperatorState.CONSENSUS_BLOCKED
    assert not report.can_issue
    assert report.consensus is None
    assert "consensus" in report.reason.lower()


def test_operator_split_brain_issue_is_blocked_before_ticket_creation():
    env = ConsensusFailoverEnvironment()
    rogue = Source(
        count=5,
        now=env.now,
    )
    divergent = Replica(
        "replica-c",
        "zone-c",
        rogue,
    )
    divergent.sync()
    env.fleet = DurableReplicaFleet(
        "primary",
        (
            env.replicas["replica-a"].member,
            env.replicas["replica-b"].member,
            divergent.member,
        ),
        policy=env.fleet_policy,
        clock=lambda: env.now[0],
    )
    env.coordinator.fleet = env.fleet
    operator = DurableFailoverOperator(
        env.target.manager,
        env.coordinator,
        fleet=env.fleet,
        clock=lambda: env.now[0],
    )
    with pytest.raises(Exception, match="cannot be issued"):
        operator.issue()
    assert env.registry.current(fp("0")) is None


def test_operator_report_serializes_consensus_commitment():
    env = ConsensusFailoverEnvironment()
    report = make_operator(env).inspect()
    data = report.to_dict()
    assert data["state"] == "ready"
    assert data["consensus"] is not None
    assert data["consensus"]["certifiable"] is True
    assert data["consensus_history"] is None
    assert data["digest"] == report.digest


def test_operator_report_serializes_consensus_history_after_issue():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    issued = operator.issue()
    data = issued.report.to_dict()
    assert data["consensus_history"] is not None
    assert data["consensus_history"]["epoch"]["generation"] == 1
    assert (
        data["consensus_history"]["epoch"]["journal_root"]
        == issued.ticket.ticket.journal_root
    )


def test_operator_report_digest_binds_consensus_state():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    first = operator.inspect()
    env.grow_and_sync()
    second = operator.inspect()
    assert first.digest != second.digest
    assert first.consensus.state_digest != second.consensus.state_digest


def test_operator_report_digest_binds_history_state():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    before = operator.inspect()
    env.coordinator.issue()
    after = operator.inspect()
    assert before.digest != after.digest
    assert before.consensus_history is None
    assert after.consensus_history is not None


def test_operator_claimed_state_takes_precedence_over_later_consensus_drift():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    issued = operator.issue()
    claimed = operator.claim(
        issued.ticket,
        consumer_id="operator",
    )
    assert claimed.state is DurableFailoverOperatorState.CLAIMED
    env.grow_and_sync()
    recovered = operator.inspect(
        ticket_id=issued.ticket.ticket.ticket_id
    )
    assert recovered.state is DurableFailoverOperatorState.CLAIMED
    assert recovered.failover is not None


def test_operator_applied_state_remains_terminal_after_later_growth():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    issued = operator.issue()
    operator.claim(
        issued.ticket,
        consumer_id="operator",
    )
    applied = operator.complete(
        issued.ticket,
        consumer_id="operator",
    )
    assert applied.state is DurableFailoverOperatorState.APPLIED
    env.grow_and_sync()
    recovered = operator.inspect(
        ticket_id=issued.ticket.ticket.ticket_id
    )
    assert recovered.state is DurableFailoverOperatorState.APPLIED
    assert recovered.terminal


def test_operator_cancelled_state_remains_terminal_after_consensus_change():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    issued = operator.issue()
    operator.claim(
        issued.ticket,
        consumer_id="operator",
    )
    cancelled = operator.cancel(
        issued.ticket,
        consumer_id="operator",
    )
    assert cancelled.state is DurableFailoverOperatorState.CANCELLED
    env.grow_and_sync()
    recovered = operator.inspect(
        ticket_id=issued.ticket.ticket.ticket_id
    )
    assert recovered.state is DurableFailoverOperatorState.CANCELLED


def test_operator_without_consensus_preserves_legacy_ready_report():
    env = ConsensusFailoverEnvironment(
        strict_history=False
    )
    coordinator = DurableFailoverCoordinator(
        env.target.manager,
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=env.fleet,
    )
    operator = DurableFailoverOperator(
        env.target.manager,
        coordinator,
        fleet=env.fleet,
        clock=lambda: env.now[0],
    )
    report = operator.inspect()
    assert report.state is DurableFailoverOperatorState.READY
    assert report.consensus is None
    assert report.consensus_history is None


def test_operator_consensus_without_history_reports_consensus_only():
    env = ConsensusFailoverEnvironment(
        strict_history=False
    )
    coordinator = DurableFailoverCoordinator(
        env.target.manager,
        env.authority,
        env.registry,
        source_id="primary",
        target_id="replica-a",
        fleet=env.fleet,
        consensus=env.consensus,
    )
    operator = DurableFailoverOperator(
        env.target.manager,
        coordinator,
        fleet=env.fleet,
        clock=lambda: env.now[0],
    )
    report = operator.inspect()
    assert report.can_issue
    assert report.consensus is not None
    assert report.consensus_history is None


def test_operator_history_corruption_is_history_blocked():
    env = ConsensusFailoverEnvironment()
    operator = make_operator(env)
    operator.issue()
    current = env.history.current("primary")
    key = env.history._epoch_key(
        current.epoch.digest
    )
    record = env.registry_backend.get(
        env.history.namespace,
        key,
    )
    env.registry_backend.compare_and_swap(
        env.history.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            current.epoch,
            fleet_policy_digest=fp("9"),
        ),
    )
    report = operator.inspect()
    assert report.state is DurableFailoverOperatorState.HISTORY_BLOCKED
    assert not report.can_issue


def test_operator_report_type_checks_consensus_fields():
    env = ConsensusFailoverEnvironment()
    report = make_operator(env).inspect()
    with pytest.raises(TypeError, match="consensus"):
        replace(
            report,
            consensus=object(),
        )
    with pytest.raises(TypeError, match="consensus_history"):
        replace(
            report,
            consensus_history=object(),
        )


def test_operator_ready_report_consensus_head_matches_replication_head():
    env = ConsensusFailoverEnvironment()
    report = make_operator(env).inspect()
    selected = report.consensus.selected
    assert selected is not None
    assert (
        selected.head.journal_root
        == report.replication.journal.source_root
    )
    assert (
        selected.head.receipt_root
        == report.replication.receipts.source_root
    )
