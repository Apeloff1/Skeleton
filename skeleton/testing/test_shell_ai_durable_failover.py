"""Signed durable replica failover authorization tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_maintenance import (
    DurableMaintenanceConflict,
    DurableMaintenanceOperation,
    DurableMaintenanceResource,
    DurableMaintenanceStore,
)
from skeleton.shells.ai.durable_failover import (
    FAILOVER_ARTIFACT_TYPE,
    DurableFailoverAuthority,
    DurableFailoverConflict,
    DurableFailoverCoordinator,
    DurableFailoverPhase,
    DurableFailoverRecord,
    DurableFailoverRegistry,
    DurableFailoverTicket,
    DurableFailoverTicketError,
    SignedDurableFailoverTicket,
)
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicator,
    DurableEvidenceReplicaManager,
    DurableReplicationPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner, SignedArtifact
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


class Environment:
    def __init__(
        self,
        *,
        count=2,
        now=100.0,
        synced=True,
        maintenance=False,
        maintenance_store=None,
    ):
        self.now = [float(now)]
        self.source_backend = InMemoryFencedStore()
        self.target_backend = InMemoryFencedStore()
        self.registry_backend = InMemoryFencedStore()
        self.source_journal = DistributedAIDecisionJournal(
            self.source_backend,
            namespace="journal",
            clock=lambda: self.now[0],
        )
        self.target_journal = DistributedAIDecisionJournal(
            self.target_backend,
            namespace="journal",
            clock=lambda: self.now[0],
        )
        self.source_receipts = DistributedReceiptChain(
            self.source_backend,
            namespace="receipts",
        )
        self.target_receipts = DistributedReceiptChain(
            self.target_backend,
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
        policy = DurableReplicationPolicy(
            max_batch_items=2,
            max_batches_per_run=16,
        )
        self.journal_replica = DurableChainReplicator(
            "journal",
            self.source_journal,
            self.target_journal,
            policy=policy,
        )
        self.receipt_replica = DurableChainReplicator(
            "receipts",
            self.source_receipts,
            self.target_receipts,
            policy=policy,
        )
        self.manager = DurableEvidenceReplicaManager(
            self.journal_replica,
            self.receipt_replica,
            policy=policy,
        )
        if synced:
            self.manager.sync()
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
            nonce_factory=lambda: "nonce-fixed",
        )
        self.registry = DurableFailoverRegistry(
            self.registry_backend,
            namespace="failover",
            clock=lambda: self.now[0],
        )
        self.maintenance = maintenance_store
        if maintenance and self.maintenance is None:
            self.maintenance = DurableMaintenanceStore(
                self.registry_backend,
                ArtifactSigner(
                    "maintenance-key",
                    b"m" * 32,
                    clock=lambda: self.now[0],
                ),
                namespace="maintenance",
                clock=lambda: self.now[0],
                nonce_factory=lambda: (
                    f"maintenance-{self.now[0]}"
                ),
            )
        self.coordinator = DurableFailoverCoordinator(
            self.manager,
            self.authority,
            self.registry,
            source_id="primary",
            target_id="replica",
            maintenance=self.maintenance,
        )

    def acquire_maintenance(
        self,
        *,
        operation=DurableMaintenanceOperation.FAILOVER,
        owner_id="failover-operator",
    ):
        if self.maintenance is None:
            raise RuntimeError(
                "fixture maintenance is not enabled"
            )
        return self.maintenance.acquire(
            operation,
            owner_id=owner_id,
            resources=(
                self.coordinator
                .maintenance_resources()
            ),
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

    def advance_both_identically(self):
        self.advance_source()
        self.manager.sync()


def test_issue_binds_both_replication_roots():
    env = Environment()
    signed = env.coordinator.issue()
    ticket = signed.ticket
    report = env.manager.require_promotion_ready()
    assert ticket.source_id == "primary"
    assert ticket.target_id == "replica"
    assert ticket.replication_report_digest == report.digest
    assert ticket.policy_digest == report.policy_digest
    assert ticket.journal_sequence == report.journal.source_sequence
    assert ticket.journal_root == report.journal.source_root
    assert ticket.receipt_sequence == report.receipts.source_sequence
    assert ticket.receipt_root == report.receipts.source_root
    assert signed.signature.artifact_type == FAILOVER_ARTIFACT_TYPE
    assert signed.signature.artifact_digest == ticket.digest


def test_ticket_id_is_deterministic_for_same_inputs():
    values = dict(
        source_id="primary",
        target_id="replica",
        issued_at=1.0,
        expires_at=2.0,
        nonce="nonce",
        replication_report_digest=fp("a"),
        journal_root=fp("b"),
        receipt_root=fp("c"),
    )
    assert DurableFailoverTicket.derive_id(**values) == (
        DurableFailoverTicket.derive_id(**values)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "other"),
        ("target_id", "other"),
        ("issued_at", 1.5),
        ("expires_at", 3.0),
        ("nonce", "other"),
        ("replication_report_digest", fp("d")),
        ("journal_root", fp("e")),
        ("receipt_root", fp("f")),
    ],
)
def test_ticket_id_changes_with_authority_binding(field, value):
    values = dict(
        source_id="primary",
        target_id="replica",
        issued_at=1.0,
        expires_at=2.0,
        nonce="nonce",
        replication_report_digest=fp("a"),
        journal_root=fp("b"),
        receipt_root=fp("c"),
    )
    first = DurableFailoverTicket.derive_id(**values)
    values[field] = value
    second = DurableFailoverTicket.derive_id(**values)
    assert first != second


def test_issue_requires_replica_in_sync():
    env = Environment(synced=False)
    with pytest.raises(Exception):
        env.coordinator.issue()


@pytest.mark.parametrize("ttl", [0, -1, True, 301, float("inf")])
def test_issue_validates_ttl(ttl):
    env = Environment()
    with pytest.raises(ValueError, match="ttl_seconds"):
        env.coordinator.issue(ttl_seconds=ttl)


def test_static_verification_accepts_valid_ticket():
    env = Environment()
    signed = env.coordinator.issue()
    assert env.authority.verify_static(
        signed,
        source_id="primary",
        target_id="replica",
    ) == signed.ticket


def test_live_verification_accepts_current_roots():
    env = Environment()
    signed = env.coordinator.issue()
    assert env.authority.verify(
        signed,
        env.manager,
        source_id="primary",
        target_id="replica",
    ) == signed.ticket


def test_source_advance_makes_ticket_stale():
    env = Environment()
    signed = env.coordinator.issue()
    env.advance_source()
    with pytest.raises(
        DurableFailoverTicketError,
        match="no longer promotion ready",
    ):
        env.authority.verify(
            signed,
            env.manager,
        )


def test_source_and_target_advance_together_still_make_old_ticket_stale():
    env = Environment()
    signed = env.coordinator.issue()
    env.advance_both_identically()
    assert env.manager.require_promotion_ready().promotion_ready
    with pytest.raises(
        DurableFailoverTicketError,
        match="differs",
    ):
        env.authority.verify(
            signed,
            env.manager,
        )


def test_expired_ticket_is_rejected():
    env = Environment()
    signed = env.coordinator.issue(ttl_seconds=10)
    env.now[0] = 111.0
    with pytest.raises(
        DurableFailoverTicketError,
        match="expired",
    ):
        env.authority.verify_static(signed)


def test_static_verification_can_authenticate_expired_historical_ticket():
    env = Environment()
    signed = env.coordinator.issue(ttl_seconds=10)
    env.now[0] = 1000.0
    assert env.authority.verify_static(
        signed,
        enforce_time=False,
    ) == signed.ticket


def test_future_ticket_is_rejected():
    env = Environment()
    signed = env.coordinator.issue()
    env.now[0] = 0.0
    with pytest.raises(
        DurableFailoverTicketError,
        match="future",
    ):
        env.authority.verify_static(signed)


def test_signature_tamper_is_rejected():
    env = Environment()
    signed = env.coordinator.issue()
    bad_signature = replace(
        signed.signature,
        signature="0" * 64,
    )
    forged = SignedDurableFailoverTicket(
        signed.ticket,
        bad_signature,
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="signature",
    ):
        env.authority.verify_static(forged)


def test_wrong_signer_key_rejects_ticket():
    env = Environment()
    signed = env.coordinator.issue()
    other = DurableFailoverAuthority(
        ArtifactSigner(
            "failover-key",
            b"q" * 32,
            clock=lambda: env.now[0],
        ),
        clock=lambda: env.now[0],
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="signature",
    ):
        other.verify_static(signed)


def test_wrong_signer_id_rejects_ticket():
    env = Environment()
    signed = env.coordinator.issue()
    other = DurableFailoverAuthority(
        ArtifactSigner(
            "other-key",
            b"k" * 32,
            clock=lambda: env.now[0],
        ),
        clock=lambda: env.now[0],
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="signature",
    ):
        other.verify_static(signed)


def test_signed_metadata_mismatch_is_rejected_even_with_valid_signature():
    env = Environment()
    signed = env.coordinator.issue()
    wrong = env.signer.sign(
        FAILOVER_ARTIFACT_TYPE,
        signed.ticket.digest,
        metadata={
            "ticket_id": signed.ticket.ticket_id,
            "source_id": "wrong",
            "target_id": signed.ticket.target_id,
            "expires_at": repr(signed.ticket.expires_at),
        },
    )
    forged = SignedDurableFailoverTicket(
        signed.ticket,
        wrong,
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="metadata",
    ):
        env.authority.verify_static(forged)


def test_expected_source_identity_is_enforced():
    env = Environment()
    signed = env.coordinator.issue()
    with pytest.raises(
        DurableFailoverTicketError,
        match="source_id",
    ):
        env.authority.verify_static(
            signed,
            source_id="wrong",
        )


def test_expected_target_identity_is_enforced():
    env = Environment()
    signed = env.coordinator.issue()
    with pytest.raises(
        DurableFailoverTicketError,
        match="target_id",
    ):
        env.authority.verify_static(
            signed,
            target_id="wrong",
        )


def test_first_claim_is_persisted():
    env = Environment()
    signed = env.coordinator.issue()
    stored = env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    assert stored.revision == 1
    assert stored.record.phase is DurableFailoverPhase.CLAIMED
    assert stored.record.consumer_id == "operator-1"
    assert stored.record.ticket_id == signed.ticket.ticket_id
    assert not stored.record.terminal


def test_same_consumer_claim_is_idempotent():
    env = Environment()
    signed = env.coordinator.issue()
    first = env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    second = env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    assert second == first
    assert second.revision == 1


def test_other_consumer_cannot_claim_same_ticket():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    with pytest.raises(
        DurableFailoverConflict,
        match="another consumer",
    ):
        env.coordinator.claim(
            signed,
            consumer_id="operator-2",
        )


def test_complete_transitions_claim_to_applied():
    env = Environment()
    signed = env.coordinator.issue()
    claim = env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    applied = env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    )
    assert applied.revision > claim.revision
    assert applied.record.phase is DurableFailoverPhase.APPLIED
    assert applied.record.terminal
    assert (
        applied.record.applied_report_digest
        == env.manager.require_promotion_ready().digest
    )


def test_complete_is_idempotent_after_apply():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    first = env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    )
    second = env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    )
    assert second == first


def test_idempotent_complete_still_verifies_ticket_signature():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    )
    forged = SignedDurableFailoverTicket(
        signed.ticket,
        replace(
            signed.signature,
            signature="0" * 64,
        ),
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="signature",
    ):
        env.coordinator.complete(
            forged,
            consumer_id="operator-1",
        )


def test_idempotent_complete_survives_expiry_after_apply():
    env = Environment()
    signed = env.coordinator.issue(ttl_seconds=5)
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    applied = env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    )
    env.now[0] = 1000.0
    assert env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    ) == applied


def test_idempotent_complete_survives_source_growth_after_apply():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    applied = env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    )
    env.advance_source()
    assert env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    ) == applied


def test_other_consumer_cannot_idempotently_complete_applied_claim():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.coordinator.complete(
        signed,
        consumer_id="operator-1",
    )
    with pytest.raises(
        DurableFailoverConflict,
        match="owner",
    ):
        env.coordinator.complete(
            signed,
            consumer_id="operator-2",
        )


def test_source_advance_between_claim_and_complete_blocks_apply():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.advance_source()
    with pytest.raises(
        DurableFailoverTicketError,
        match="no longer promotion ready",
    ):
        env.coordinator.complete(
            signed,
            consumer_id="operator-1",
        )
    current = env.registry.current(
        signed.ticket.ticket_id
    )
    assert current.record.phase is DurableFailoverPhase.CLAIMED


def test_resync_after_claim_does_not_make_old_ticket_current_again():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.advance_source()
    env.manager.sync()
    assert env.manager.require_promotion_ready().promotion_ready
    with pytest.raises(
        DurableFailoverTicketError,
        match="differs",
    ):
        env.coordinator.complete(
            signed,
            consumer_id="operator-1",
        )


def test_claim_can_be_cancelled_after_ticket_becomes_stale():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.advance_source()
    cancelled = env.coordinator.cancel(
        signed,
        consumer_id="operator-1",
    )
    assert cancelled.record.phase is DurableFailoverPhase.CANCELLED
    assert cancelled.record.terminal


def test_cancel_authenticates_signature():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    forged = SignedDurableFailoverTicket(
        signed.ticket,
        replace(
            signed.signature,
            signature="0" * 64,
        ),
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="signature",
    ):
        env.coordinator.cancel(
            forged,
            consumer_id="operator-1",
        )


def test_cancel_is_idempotent_for_same_owner():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    first = env.coordinator.cancel(
        signed,
        consumer_id="operator-1",
    )
    second = env.coordinator.cancel(
        signed,
        consumer_id="operator-1",
    )
    assert second == first


def test_cancelled_claim_cannot_be_applied():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.coordinator.cancel(
        signed,
        consumer_id="operator-1",
    )
    with pytest.raises(
        DurableFailoverConflict,
        match="terminal",
    ):
        env.coordinator.complete(
            signed,
            consumer_id="operator-1",
        )


def test_other_consumer_cannot_cancel_claim():
    env = Environment()
    signed = env.coordinator.issue()
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    with pytest.raises(
        DurableFailoverConflict,
        match="owner",
    ):
        env.coordinator.cancel(
            signed,
            consumer_id="operator-2",
        )


def test_complete_requires_prior_claim():
    env = Environment()
    signed = env.coordinator.issue()
    with pytest.raises(
        DurableFailoverConflict,
        match="not claimed",
    ):
        env.coordinator.complete(
            signed,
            consumer_id="operator-1",
        )


def test_cancel_requires_prior_claim():
    env = Environment()
    signed = env.coordinator.issue()
    with pytest.raises(
        DurableFailoverConflict,
        match="not claimed",
    ):
        env.coordinator.cancel(
            signed,
            consumer_id="operator-1",
        )


def test_expired_ticket_cannot_be_newly_claimed():
    env = Environment()
    signed = env.coordinator.issue(ttl_seconds=5)
    env.now[0] = 106.0
    with pytest.raises(
        DurableFailoverTicketError,
        match="expired",
    ):
        env.coordinator.claim(
            signed,
            consumer_id="operator-1",
        )


def test_claimed_ticket_that_expires_before_complete_cannot_apply():
    env = Environment()
    signed = env.coordinator.issue(ttl_seconds=5)
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.now[0] = 106.0
    with pytest.raises(
        DurableFailoverTicketError,
        match="expired",
    ):
        env.coordinator.complete(
            signed,
            consumer_id="operator-1",
        )


def test_expired_claim_can_still_be_cancelled():
    env = Environment()
    signed = env.coordinator.issue(ttl_seconds=5)
    env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    env.now[0] = 106.0
    cancelled = env.coordinator.cancel(
        signed,
        consumer_id="operator-1",
    )
    assert cancelled.record.phase is DurableFailoverPhase.CANCELLED


def test_registry_rejects_ticket_id_rebinding():
    env = Environment()
    signed = env.coordinator.issue()
    env.registry.claim(
        signed.ticket,
        consumer_id="operator-1",
    )
    rebound = replace(
        signed.ticket,
        nonce="other",
    )
    with pytest.raises(
        DurableFailoverConflict,
        match="different failover ticket",
    ):
        env.registry.claim(
            rebound,
            consumer_id="operator-1",
        )


def test_registry_current_missing_returns_none():
    env = Environment()
    assert env.registry.current(fp("f")) is None


def test_registry_key_hides_ticket_id():
    key = DurableFailoverRegistry._key(fp("a"))
    assert key.startswith("ticket:")
    assert fp("a") not in key


class ConflictOnceTransitionBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflict = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if not self.conflict:
            self.conflict = True
            raise DistributedStateConflict("synthetic")
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(self, namespace, key, *, expected_revision):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_registry_terminal_transition_retries_cas_conflict():
    env = Environment()
    backend = ConflictOnceTransitionBackend()
    registry = DurableFailoverRegistry(
        backend,
        namespace="failover",
        clock=lambda: env.now[0],
    )
    ticket = env.coordinator.issue().ticket
    registry.claim(
        ticket,
        consumer_id="operator-1",
    )
    applied = registry.applied(
        ticket,
        consumer_id="operator-1",
        replication_report_digest=env.manager.inspect().digest,
    )
    assert applied.record.phase is DurableFailoverPhase.APPLIED


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_ttl_seconds": 0},
        {"max_ttl_seconds": float("inf")},
        {"max_clock_skew_seconds": 0},
        {"max_clock_skew_seconds": True},
    ],
)
def test_authority_configuration_validation(kwargs):
    signer = ArtifactSigner("key", b"k" * 32)
    with pytest.raises(ValueError):
        DurableFailoverAuthority(
            signer,
            **kwargs,
        )


def test_authority_requires_signer():
    with pytest.raises(TypeError, match="ArtifactSigner"):
        DurableFailoverAuthority(object())


def test_authority_requires_callable_clock():
    with pytest.raises(TypeError, match="clock"):
        DurableFailoverAuthority(
            ArtifactSigner("key", b"k" * 32),
            clock=object(),
        )


def test_authority_requires_callable_nonce_factory():
    with pytest.raises(TypeError, match="nonce_factory"):
        DurableFailoverAuthority(
            ArtifactSigner("key", b"k" * 32),
            nonce_factory=object(),
        )


def test_invalid_nonce_factory_is_rejected_at_issue():
    env = Environment()
    authority = DurableFailoverAuthority(
        env.signer,
        clock=lambda: env.now[0],
        nonce_factory=lambda: "",
    )
    with pytest.raises(
        DurableFailoverTicketError,
        match="nonce",
    ):
        authority.issue(
            env.manager,
            source_id="primary",
            target_id="replica",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"namespace": ""},
        {"namespace": "x" * 129},
        {"max_cas_retries": 0},
        {"max_cas_retries": 65},
        {"max_cas_retries": True},
    ],
)
def test_registry_configuration_validation(kwargs):
    with pytest.raises(ValueError):
        DurableFailoverRegistry(
            InMemoryFencedStore(),
            **kwargs,
        )


def test_registry_requires_callable_clock():
    with pytest.raises(TypeError, match="clock"):
        DurableFailoverRegistry(
            InMemoryFencedStore(),
            clock=object(),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"ticket_id": "bad"},
        {"source_id": ""},
        {"target_id": ""},
        {"issued_at": -1.0},
        {"expires_at": -1.0},
        {"nonce": ""},
        {"replication_report_digest": "bad"},
        {"policy_digest": "bad"},
        {"journal_sequence": -1},
        {"journal_root": "bad"},
        {"receipt_sequence": -1},
        {"receipt_root": "bad"},
    ],
)
def test_ticket_validation(kwargs):
    values = dict(
        schema_version=1,
        ticket_id=fp("a"),
        source_id="primary",
        target_id="replica",
        issued_at=1.0,
        expires_at=2.0,
        nonce="nonce",
        replication_report_digest=fp("b"),
        policy_digest=fp("c"),
        journal_sequence=1,
        journal_root=fp("d"),
        receipt_sequence=1,
        receipt_root=fp("e"),
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableFailoverTicket(**values)


def test_ticket_rejects_same_source_target():
    with pytest.raises(ValueError, match="differ"):
        DurableFailoverTicket(
            1,
            fp("a"),
            "same",
            "same",
            1.0,
            2.0,
            "nonce",
            fp("b"),
            fp("c"),
            1,
            fp("d"),
            1,
            fp("e"),
        )


def test_ticket_rejects_nonpositive_lifetime():
    with pytest.raises(ValueError, match="expiry"):
        DurableFailoverTicket(
            1,
            fp("a"),
            "primary",
            "replica",
            2.0,
            2.0,
            "nonce",
            fp("b"),
            fp("c"),
            1,
            fp("d"),
            1,
            fp("e"),
        )


def test_signed_ticket_rejects_wrong_artifact_type():
    env = Environment()
    signed = env.coordinator.issue()
    wrong = replace(
        signed.signature,
        artifact_type="wrong",
    )
    with pytest.raises(ValueError, match="artifact type"):
        SignedDurableFailoverTicket(
            signed.ticket,
            wrong,
        )


def test_signed_ticket_rejects_wrong_digest_binding():
    env = Environment()
    signed = env.coordinator.issue()
    wrong = replace(
        signed.signature,
        artifact_digest=fp("f"),
    )
    with pytest.raises(ValueError, match="bind"):
        SignedDurableFailoverTicket(
            signed.ticket,
            wrong,
        )


def test_failover_record_validation():
    with pytest.raises(ValueError):
        DurableFailoverRecord(
            2,
            fp("a"),
            fp("b"),
            fp("c"),
            "primary",
            "replica",
            "consumer",
            DurableFailoverPhase.CLAIMED,
            1.0,
            1.0,
        )
    with pytest.raises(ValueError):
        DurableFailoverRecord(
            1,
            fp("a"),
            fp("b"),
            fp("c"),
            "primary",
            "replica",
            "consumer",
            DurableFailoverPhase.APPLIED,
            1.0,
            1.0,
        )


def test_applied_record_requires_digest_and_nonapplied_forbids_it():
    with pytest.raises(ValueError, match="requires report"):
        DurableFailoverRecord(
            1,
            fp("a"),
            fp("b"),
            fp("c"),
            "primary",
            "replica",
            "consumer",
            DurableFailoverPhase.APPLIED,
            1.0,
            1.0,
            "",
        )
    with pytest.raises(ValueError, match="may not bind"):
        DurableFailoverRecord(
            1,
            fp("a"),
            fp("b"),
            fp("c"),
            "primary",
            "replica",
            "consumer",
            DurableFailoverPhase.CLAIMED,
            1.0,
            1.0,
            fp("d"),
        )


def test_record_claim_id_is_deterministic():
    first = DurableFailoverRecord.derive_claim_id(
        fp("a"),
        "consumer",
    )
    second = DurableFailoverRecord.derive_claim_id(
        fp("a"),
        "consumer",
    )
    assert first == second
    assert len(first) == 64


def test_ticket_and_record_serialization():
    env = Environment()
    signed = env.coordinator.issue()
    stored = env.coordinator.claim(
        signed,
        consumer_id="operator-1",
    )
    assert signed.to_dict()["ticket_digest"] == signed.ticket.digest
    assert stored.record.to_dict()["phase"] == "claimed"
    assert stored.record.to_dict()["terminal"] is False


def test_coordinator_identity_must_differ():
    env = Environment()
    with pytest.raises(ValueError, match="differ"):
        DurableFailoverCoordinator(
            env.manager,
            env.authority,
            env.registry,
            source_id="same",
            target_id="same",
        )


def test_coordinator_type_validation():
    env = Environment()
    with pytest.raises(TypeError, match="manager"):
        DurableFailoverCoordinator(
            object(),
            env.authority,
            env.registry,
            source_id="a",
            target_id="b",
        )
    with pytest.raises(TypeError, match="authority"):
        DurableFailoverCoordinator(
            env.manager,
            object(),
            env.registry,
            source_id="a",
            target_id="b",
        )
    with pytest.raises(TypeError, match="registry"):
        DurableFailoverCoordinator(
            env.manager,
            env.authority,
            object(),
            source_id="a",
            target_id="b",
        )


def test_two_tickets_can_be_claimed_independently():
    env = Environment()
    first = env.coordinator.issue()
    env.now[0] += 1.0
    env.authority._nonce_factory = lambda: "nonce-two"
    second = env.coordinator.issue()
    assert first.ticket.ticket_id != second.ticket.ticket_id
    one = env.coordinator.claim(
        first,
        consumer_id="operator-1",
    )
    two = env.coordinator.claim(
        second,
        consumer_id="operator-2",
    )
    assert one.record.ticket_id != two.record.ticket_id
