"""Single-chain post-compaction proof integration and adversarial tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import (
    DurableArchiveManifestBuilder,
    DurableArchiveVerification,
)
from skeleton.shells.ai.durable_archive_store import (
    DurableArchiveRepository,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionPolicy,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificateStore,
    SignedDurableCompactionCertificate,
)
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionExecution,
    DurableCompactionOperator,
    DurableCompactionWorkflow,
)
from skeleton.shells.ai.durable_compaction_proof import (
    DurableCompactionProof,
    DurableCompactionProofBuilder,
    DurableCompactionProofError,
    DurableCompactionProofVerification,
    SignedDurableCompactionProof,
)
from skeleton.shells.ai.durable_compaction_reservation import (
    DurableCompactionReservationStore,
    SignedDurableCompactionReservation,
)
from skeleton.shells.ai.durable_hot_floor import DurableHotFloorStore
from skeleton.shells.ai.durable_pruning import (
    DurablePruningExecutor,
    DurablePruningResult,
)
from skeleton.shells.ai.durable_pruning_authorization import (
    DurablePruningAuthorizationStore,
    SignedDurablePruningAuthorization,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def signer(
    name: str,
    char: bytes,
    *,
    clock=lambda: 400.0,
) -> ArtifactSigner:
    return ArtifactSigner(
        name,
        char * 32,
        clock=clock,
    )


def receipt(index: int) -> ExecutionReceipt:
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
        stdout_bytes=index + 1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
        metadata={"index": index},
    )


def append_events(
    journal: DistributedAIDecisionJournal,
    count: int,
    *,
    start: int = 0,
):
    return tuple(
        journal.append(
            "proof.event",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
            summary=f"event {index}",
            data={"index": index},
        )
        for index in range(start, start + count)
    )


class ProofFixture:
    def __init__(
        self,
        *,
        kind: str = "journal",
    ) -> None:
        self.kind = kind
        self.now = [400.0]
        self.backend = InMemoryFencedStore()
        self.floor_signer = signer(
            "proof-floor",
            b"f",
            clock=lambda: self.now[0],
        )
        self.floor_store = DurableHotFloorStore(
            self.backend,
            self.floor_signer,
            namespace=f"{kind}-proof-floors",
            clock=lambda: self.now[0],
        )

        if kind == "journal":
            self.chain = DistributedAIDecisionJournal(
                self.backend,
                namespace="proof-journal",
                max_events=32,
                clock=lambda: 10.0,
                hot_floor_store=self.floor_store,
                hot_floor_chain_id="journal",
            )
            self.chain_id = "journal"
            self.first = append_events(
                self.chain,
                6,
            )
        elif kind == "receipts":
            self.chain = DistributedReceiptChain(
                self.backend,
                namespace="proof-receipts",
                max_receipts=32,
                hot_floor_store=self.floor_store,
                hot_floor_chain_id="receipts",
            )
            self.chain_id = "receipts"
            self.first = tuple(
                self.chain.append(receipt(index))
                for index in range(6)
            )
        else:
            raise ValueError("unsupported proof fixture kind")

        self.checkpoint_signer = signer(
            "proof-checkpoint",
            b"c",
            clock=lambda: 100.0,
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            self.checkpoint_signer,
            namespace=f"{kind}-proof-checkpoints",
            clock=lambda: 100.0,
        )
        self.archive_signer = signer(
            "proof-archive",
            b"a",
            clock=lambda: 200.0,
        )
        self.archive_builder = DurableArchiveManifestBuilder(
            self.checkpoints,
            self.archive_signer,
            clock=lambda: 200.0,
        )
        self.archives = DurableArchiveRepository(
            self.backend,
            self.checkpoints,
            self.archive_signer,
            namespace=f"{kind}-proof-archives",
            clock=lambda: 300.0,
        )
        self.checkpoint = self.checkpoints.publish(
            self.chain_id,
            self.chain,
        )
        self.archive = self.archive_builder.build(
            self.checkpoint,
            self.chain,
        )
        self.archives.put(
            self.archive,
            self.checkpoint,
            self.chain,
        )

        if kind == "journal":
            self.later = append_events(
                self.chain,
                2,
                start=6,
            )
        else:
            self.later = tuple(
                self.chain.append(receipt(index))
                for index in range(6, 8)
            )

        self.archive_verification = (
            self.archive_builder.require(
                self.archive,
                self.checkpoint,
                self.chain,
            )
        )
        assert self.archive_verification.valid
        assert self.archive_verification.current_sequence == 8

        self.retention_planner = DurableRetentionPlanner(
            self.checkpoints,
            DurableRetentionPolicy(
                minimum_live_tail=2,
                minimum_archive_batch=2,
                target_utilization=0.25,
                warning_utilization=0.75,
                critical_utilization=0.95,
                max_protected_roots=32,
            ),
        )
        self.retention = self.retention_planner.plan(
            self.chain_id,
            self.chain,
        )
        self.compaction = DurableCompactionPlanner(
            self.archives,
            DurableCompactionPolicy(
                minimum_live_tail=2,
                maximum_candidate_nodes=20,
                max_protected_roots=32,
            ),
        )
        readiness = self.compaction.require_ready(
            self.retention,
            self.chain,
        )
        assert readiness.ready
        assert readiness.cutoff_sequence == 6

        self.certificate_signer = signer(
            "proof-certificate",
            b"s",
            clock=lambda: self.now[0],
        )
        self.certificates = DurableCompactionCertificateStore(
            self.backend,
            self.certificate_signer,
            self.compaction,
            namespace=f"{kind}-proof-certificates",
            ttl_seconds=120.0,
            max_ttl_seconds=3600.0,
            clock=lambda: self.now[0],
        )

        auth_nonce = [0]

        def next_auth_nonce():
            auth_nonce[0] += 1
            return f"auth-{kind}-{auth_nonce[0]}"

        self.authorization_signer = signer(
            "proof-authorization",
            b"p",
            clock=lambda: self.now[0],
        )
        self.authorizations = DurablePruningAuthorizationStore(
            self.backend,
            self.authorization_signer,
            self.certificates,
            namespace=f"{kind}-proof-authorizations",
            ttl_seconds=120.0,
            max_ttl_seconds=600.0,
            max_delete_items=100,
            clock=lambda: self.now[0],
            nonce_factory=next_auth_nonce,
        )
        self.executor = DurablePruningExecutor(
            self.backend,
            self.authorizations,
            self.floor_store,
            namespace=f"{kind}-proof-pruning",
            max_items=100,
            clock=lambda: self.now[0],
        )

        reservation_nonce = [0]

        def next_reservation_nonce():
            reservation_nonce[0] += 1
            return (
                f"reservation-{kind}-"
                f"{reservation_nonce[0]}"
            )

        self.reservation_signer = signer(
            "proof-reservation",
            b"r",
            clock=lambda: self.now[0],
        )
        self.reservations = DurableCompactionReservationStore(
            self.backend,
            self.reservation_signer,
            namespace=f"{kind}-proof-reservations",
            ttl_seconds=120.0,
            max_ttl_seconds=3600.0,
            clock=lambda: self.now[0],
            nonce_factory=next_reservation_nonce,
        )
        self.operator = DurableCompactionOperator(
            self.backend,
            self.compaction,
            self.certificates,
            self.authorizations,
            self.executor,
            reservations=self.reservations,
            namespace=f"{kind}-proof-workflows",
            clock=lambda: self.now[0],
        )
        self.proof_signer = signer(
            "proof-evidence",
            b"z",
            clock=lambda: self.now[0],
        )
        self.builder = DurableCompactionProofBuilder(
            self.proof_signer,
            certificate_signer=self.certificate_signer,
            authorization_signer=self.authorization_signer,
            reservation_signer=self.reservation_signer,
            archive_signer=self.archive_signer,
            floor_signer=self.floor_signer,
            clock=lambda: self.now[0],
        )

    def complete(self):
        planned = self.operator.plan(
            self.retention,
            self.chain,
            operator_id="operator",
        )
        holder_id = planned.workflow_id
        reservation = self.reservations.acquire(
            self.chain_id,
            holder_id=holder_id,
            operator_id="operator",
        )
        certificate = self.operator.certify(
            planned.workflow_id,
            self.retention,
            self.chain,
            reservation_holder_id=holder_id,
        )
        authorization = self.operator.authorize(
            planned.workflow_id,
            self.retention,
            self.chain,
            reservation_holder_id=holder_id,
        )
        self.operator.prepare(
            planned.workflow_id,
            self.retention,
            self.chain,
            reservation_holder_id=holder_id,
        )
        execution = self.operator.execute(
            planned.workflow_id,
            self.retention,
            self.chain,
            reservation_holder_id=holder_id,
        )
        assert execution.ok
        workflow = execution.stored.workflow
        proof = self.builder.build(
            workflow=workflow,
            reservation=reservation,
            certificate=certificate,
            authorization=authorization,
            archive=self.archive,
            archive_verification=self.archive_verification,
            pruning=execution.result,
        )
        return {
            "workflow": workflow,
            "reservation": reservation,
            "certificate": certificate,
            "authorization": authorization,
            "execution": execution,
            "pruning": execution.result,
            "proof": proof,
        }

    def inspect(self, values, **changes):
        args = {
            "workflow": values["workflow"],
            "reservation": values["reservation"],
            "certificate": values["certificate"],
            "authorization": values["authorization"],
            "archive": self.archive,
            "archive_verification": self.archive_verification,
            "pruning": values["pruning"],
        }
        args.update(changes)
        return self.builder.inspect(
            values["proof"],
            **args,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_real_single_chain_compaction_produces_valid_proof(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    report = fixture.inspect(values)
    assert report.valid
    assert report.reasons == ()
    assert values["proof"].proof.chain_id == fixture.chain_id
    assert values["proof"].proof.workflow_id == values["workflow"].workflow_id
    assert values["proof"].proof.reservation_generation == 1
    assert values["proof"].proof.deleted_items == 6
    assert values["proof"].proof.delete_count == 6


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_post_compaction_proof_never_authorizes_destruction(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"]
    report = fixture.inspect(values)
    assert proof.destructive_action_authorized is False
    assert proof.proof.destructive_action_authorized is False
    assert report.destructive_action_authorized is False
    assert (
        proof.proof.authority
        == "post-operation-compaction-evidence"
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_signature_binds_exact_proof_digest(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"]
    assert (
        proof.signature.artifact_type
        == "shell-ai-durable-compaction-proof"
    )
    assert (
        proof.signature.artifact_digest
        == proof.proof.digest
    )
    fixture.proof_signer.verify(proof.signature)


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_exact_component_signatures(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    report = fixture.inspect(values)
    assert report.component_signatures_valid
    assert report.reservation_binding_valid
    assert report.floor_binding_valid
    assert report.authority_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_completed_workflow_digest(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"].proof
    assert proof.workflow_digest == values["workflow"].digest
    assert proof.completed_at == values["workflow"].updated_at


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_archive_verification_digest(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    expected = fixture.builder._archive_verification_digest(
        fixture.archive_verification
    )
    assert (
        values["proof"].proof.archive_verification_digest
        == expected
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_original_head_and_pruned_cutoff(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"].proof
    workflow = values["workflow"]
    assert proof.current_sequence == 8
    assert proof.current_sequence == workflow.current_sequence
    assert proof.current_root == workflow.current_root
    assert proof.cutoff_sequence == 6
    assert proof.cutoff_root == workflow.cutoff_root
    assert proof.previous_floor_sequence == 0
    assert proof.previous_floor_root == "0" * 64


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_signed_hot_floor_and_fence(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    floor = values["pruning"].floor.floor
    proof = values["proof"].proof
    assert proof.floor_id == floor.floor_id
    assert proof.floor_digest == floor.digest
    assert proof.fencing_token == floor.fencing_token
    assert floor.sequence == proof.cutoff_sequence
    assert floor.root_hash == proof.cutoff_root


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_destructive_authorization(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    auth = values["authorization"].authorization
    proof = values["proof"].proof
    assert proof.authorization_id == auth.authorization_id
    assert proof.authorization_digest == auth.digest
    assert auth.destructive_action_authorized


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_non_destructive_certificate(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    cert = values["certificate"].certificate
    proof = values["proof"].proof
    assert proof.certificate_id == cert.certificate_id
    assert proof.certificate_digest == cert.digest
    assert not cert.destructive_action_authorized


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_reservation_generation(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    reservation = values["reservation"].reservation
    proof = values["proof"].proof
    assert proof.reservation_id == reservation.reservation_id
    assert proof.reservation_digest == reservation.digest
    assert proof.reservation_generation == reservation.generation
    assert reservation.holder_id == proof.workflow_id
    assert not reservation.destructive_action_authorized


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_archive_manifest(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"].proof
    manifest = fixture.archive.manifest
    assert proof.archive_id == manifest.archive_id
    assert proof.archive_manifest_digest == manifest.digest
    assert proof.cutoff_sequence == manifest.checkpoint_sequence
    assert proof.cutoff_root == manifest.checkpoint_root


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_binds_pruning_operation_and_manifest(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"].proof
    pruning = values["pruning"]
    assert proof.pruning_operation_id == pruning.operation.operation_id
    assert proof.pruning_manifest_digest == pruning.manifest.digest
    assert proof.deleted_items == pruning.operation.deleted_items
    assert proof.delete_count == pruning.manifest.delete_count


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_id_is_content_deterministic(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"].proof
    expected = DurableCompactionProof.derive_id(
        workflow_id=proof.workflow_id,
        workflow_digest=proof.workflow_digest,
        reservation_id=proof.reservation_id,
        certificate_id=proof.certificate_id,
        authorization_id=proof.authorization_id,
        pruning_operation_id=proof.pruning_operation_id,
        floor_id=proof.floor_id,
    )
    assert proof.proof_id == expected


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_serialization_is_stable(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    first = values["proof"].to_dict()
    second = values["proof"].to_dict()
    assert first == second
    assert first["destructive_action_authorized"] is False
    assert first["proof"]["digest"] == values["proof"].proof.digest
    assert (
        first["proof"]["binding_digest"]
        == values["proof"].proof.binding_digest
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_verification_serialization_is_non_authorizing(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    data = fixture.inspect(values).to_dict()
    assert data["valid"] is True
    assert data["destructive_action_authorized"] is False
    assert data["reasons"] == []


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_require_accepts_valid_proof(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    report = fixture.builder.require(
        values["proof"],
        workflow=values["workflow"],
        reservation=values["reservation"],
        certificate=values["certificate"],
        authorization=values["authorization"],
        archive=fixture.archive,
        archive_verification=fixture.archive_verification,
        pruning=values["pruning"],
    )
    assert report.valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_wrong_proof_signer_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    foreign = DurableCompactionProofBuilder(
        signer("foreign-proof", b"x"),
        certificate_signer=fixture.certificate_signer,
        authorization_signer=fixture.authorization_signer,
        reservation_signer=fixture.reservation_signer,
        archive_signer=fixture.archive_signer,
        floor_signer=fixture.floor_signer,
    )
    report = foreign.inspect(
        values["proof"],
        workflow=values["workflow"],
        reservation=values["reservation"],
        certificate=values["certificate"],
        authorization=values["authorization"],
        archive=fixture.archive,
        archive_verification=fixture.archive_verification,
        pruning=values["pruning"],
    )
    assert not report.valid
    assert any(
        "proof signature verification failed" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_missing_component_signer_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    builder = DurableCompactionProofBuilder(
        fixture.proof_signer,
        certificate_signer=fixture.certificate_signer,
        authorization_signer=fixture.authorization_signer,
        reservation_signer=None,
        archive_signer=fixture.archive_signer,
        floor_signer=fixture.floor_signer,
    )
    report = builder.inspect(
        values["proof"],
        workflow=values["workflow"],
        reservation=values["reservation"],
        certificate=values["certificate"],
        authorization=values["authorization"],
        archive=fixture.archive,
        archive_verification=fixture.archive_verification,
        pruning=values["pruning"],
    )
    assert not report.valid
    assert not report.component_signatures_valid
    assert any(
        "reservation signature signer unavailable" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_wrong_reservation_signer_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    builder = DurableCompactionProofBuilder(
        fixture.proof_signer,
        certificate_signer=fixture.certificate_signer,
        authorization_signer=fixture.authorization_signer,
        reservation_signer=signer("wrong-reservation", b"x"),
        archive_signer=fixture.archive_signer,
        floor_signer=fixture.floor_signer,
    )
    report = builder.inspect(
        values["proof"],
        workflow=values["workflow"],
        reservation=values["reservation"],
        certificate=values["certificate"],
        authorization=values["authorization"],
        archive=fixture.archive,
        archive_verification=fixture.archive_verification,
        pruning=values["pruning"],
    )
    assert not report.valid
    assert any(
        "reservation signature verification failed" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_reservation_holder_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    raw = values["reservation"].reservation
    changed = replace(
        raw,
        holder_id="foreign-holder",
    )
    signed = SignedDurableCompactionReservation(
        changed,
        fixture.reservation_signer.sign(
            "durable-compaction-reservation",
            changed.digest,
        ),
    )
    report = fixture.inspect(
        values,
        reservation=signed,
    )
    assert not report.valid
    assert not report.reservation_binding_valid
    assert any(
        "reservation holder binding mismatch" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_reservation_generation_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    raw = values["reservation"].reservation
    changed = replace(
        raw,
        generation=raw.generation + 1,
        reservation_id=DurableCompactionProof.derive_id(
            workflow_id=values["workflow"].workflow_id,
            workflow_digest=values["workflow"].digest,
            reservation_id=raw.reservation_id,
            certificate_id=values["certificate"].certificate.certificate_id,
            authorization_id=values["authorization"].authorization.authorization_id,
            pruning_operation_id=values["pruning"].operation.operation_id,
            floor_id=values["pruning"].floor.floor.floor_id,
        ),
    )
    # The altered reservation is intentionally re-signed with the correct key:
    # proof verification must still reject a valid-but-different authority.
    signed = SignedDurableCompactionReservation(
        changed,
        fixture.reservation_signer.sign(
            "durable-compaction-reservation",
            changed.digest,
        ),
    )
    report = fixture.inspect(
        values,
        reservation=signed,
    )
    assert not report.valid
    assert not report.reservation_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_certificate_digest_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    raw = values["certificate"].certificate
    changed = replace(
        raw,
        readiness_digest=fp("different-readiness"),
    )
    signed = SignedDurableCompactionCertificate(
        changed,
        fixture.certificate_signer.sign(
            "durable-compaction-readiness",
            changed.digest,
        ),
    )
    report = fixture.inspect(
        values,
        certificate=signed,
    )
    assert not report.valid
    assert not report.authority_binding_valid
    assert any(
        "readiness digest binding mismatch" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_certificate_protected_roots_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    raw = values["certificate"].certificate
    changed = replace(
        raw,
        protected_roots_digest=fp("different-protected-roots"),
    )
    signed = SignedDurableCompactionCertificate(
        changed,
        fixture.certificate_signer.sign(
            "durable-compaction-readiness",
            changed.digest,
        ),
    )
    report = fixture.inspect(
        values,
        certificate=signed,
    )
    assert not report.valid
    assert any(
        "protected roots digest binding mismatch" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_authorization_operator_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    raw = values["authorization"].authorization
    changed = replace(
        raw,
        operator_id="foreign-operator",
    )
    signed = SignedDurablePruningAuthorization(
        changed,
        fixture.authorization_signer.sign(
            "durable-pruning-authorization",
            changed.digest,
        ),
    )
    report = fixture.inspect(
        values,
        authorization=signed,
    )
    assert not report.valid
    assert any(
        "reservation operator" in reason
        or "authorization" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_authorization_delete_count_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    raw = values["authorization"].authorization
    # Preserve dataclass validity by moving both cutoff and count together.
    changed = replace(
        raw,
        previous_floor_sequence=1,
        previous_floor_root=fixture.first[0].event_hash
        if kind == "journal"
        else fixture.first[0].receipt_hash,
        delete_count=5,
    )
    signed = SignedDurablePruningAuthorization(
        changed,
        fixture.authorization_signer.sign(
            "durable-pruning-authorization",
            changed.digest,
        ),
    )
    report = fixture.inspect(
        values,
        authorization=signed,
    )
    assert not report.valid
    assert any(
        "previous floor" in reason
        or "delete count" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_verification_invalid_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    invalid = replace(
        fixture.archive_verification,
        valid=False,
        reasons=("synthetic archive failure",),
    )
    report = fixture.inspect(
        values,
        archive_verification=invalid,
    )
    assert not report.valid
    assert not report.archive_valid
    assert any(
        "archive verification is not valid" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_verification_head_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    changed = replace(
        fixture.archive_verification,
        current_sequence=9,
        current_root=fp("foreign-head"),
    )
    report = fixture.inspect(
        values,
        archive_verification=changed,
    )
    assert not report.valid
    assert any(
        "current sequence binding mismatch" in reason
        or "current root binding mismatch" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_pruning_live_verification_false_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    changed = replace(
        values["pruning"],
        live_verified=False,
    )
    report = fixture.inspect(
        values,
        pruning=changed,
    )
    assert not report.valid
    assert not report.pruning_complete


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_workflow_not_complete_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    workflow = replace(
        values["workflow"],
        phase="executing",
    )
    report = fixture.inspect(
        values,
        workflow=workflow,
    )
    assert not report.valid
    assert not report.workflow_complete


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_workflow_floor_id_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    changed = replace(
        values["workflow"],
        floor_id=fp("foreign-floor"),
    )
    report = fixture.inspect(
        values,
        workflow=changed,
    )
    assert not report.valid
    assert not report.floor_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_workflow_manifest_digest_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    changed = replace(
        values["workflow"],
        pruning_manifest_digest=fp("foreign-manifest"),
    )
    report = fixture.inspect(
        values,
        workflow=changed,
    )
    assert not report.valid
    assert not report.authority_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_id_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = replace(
        values["proof"].proof,
        proof_id=fp("foreign-proof-id"),
    )
    signed = SignedDurableCompactionProof(
        proof,
        fixture.proof_signer.sign(
            "shell-ai-durable-compaction-proof",
            proof.digest,
        ),
    )
    changed_values = dict(values)
    changed_values["proof"] = signed
    report = fixture.inspect(changed_values)
    assert not report.valid
    assert any(
        "proof_id does not match" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_proof_signature_artifact_type_substitution_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = values["proof"].proof
    signed = SignedDurableCompactionProof(
        proof,
        fixture.proof_signer.sign(
            "wrong-proof-type",
            proof.digest,
        ),
    )
    changed_values = dict(values)
    changed_values["proof"] = signed
    report = fixture.inspect(changed_values)
    assert not report.valid
    assert any(
        "proof signature artifact binding mismatch" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_component_signature_valid_but_wrong_digest_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    reservation = values["reservation"]
    signed = SignedDurableCompactionReservation(
        reservation.reservation,
        fixture.reservation_signer.sign(
            "durable-compaction-reservation",
            fp("wrong-reservation-digest"),
        ),
    )
    report = fixture.inspect(
        values,
        reservation=signed,
    )
    assert not report.valid
    assert not report.component_signatures_valid
    assert any(
        "reservation signature artifact digest mismatch" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_component_signature_valid_but_wrong_type_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    archive = fixture.archive
    changed = replace(
        archive,
        signature=fixture.archive_signer.sign(
            "wrong-archive-type",
            archive.manifest.digest,
        ),
    )
    report = fixture.inspect(
        values,
        archive=changed,
    )
    assert not report.valid
    assert not report.component_signatures_valid
    assert any(
        "archive signature artifact type mismatch" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_wrong_floor_fencing_token_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    pruning = values["pruning"]
    floor = replace(
        pruning.floor.floor,
        fencing_token=pruning.floor.floor.fencing_token + 1,
    )
    signed_floor = replace(
        pruning.floor,
        floor=floor,
        signature=fixture.floor_signer.sign(
            "durable-hot-floor",
            floor.digest,
        ),
    )
    changed = replace(
        pruning,
        floor=signed_floor,
    )
    report = fixture.inspect(
        values,
        pruning=changed,
    )
    assert not report.valid
    assert not report.floor_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_wrong_floor_archive_binding_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    pruning = values["pruning"]
    floor = replace(
        pruning.floor.floor,
        archive_id="foreign-archive",
    )
    signed_floor = replace(
        pruning.floor,
        floor=floor,
        signature=fixture.floor_signer.sign(
            "durable-hot-floor",
            floor.digest,
        ),
    )
    report = fixture.inspect(
        values,
        pruning=replace(pruning, floor=signed_floor),
    )
    assert not report.valid
    assert not report.authority_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_wrong_pruning_operation_authorization_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    pruning = values["pruning"]
    operation = replace(
        pruning.operation,
        authorization_id=fp("foreign-auth"),
    )
    report = fixture.inspect(
        values,
        pruning=replace(
            pruning,
            operation=operation,
        ),
    )
    assert not report.valid
    assert not report.authority_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_wrong_pruning_manifest_archive_is_rejected(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    pruning = values["pruning"]
    manifest = replace(
        pruning.manifest,
        archive_id="foreign-archive",
    )
    report = fixture.inspect(
        values,
        pruning=replace(
            pruning,
            manifest=manifest,
        ),
    )
    assert not report.valid
    assert not report.authority_binding_valid


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_builder_rejects_incomplete_workflow(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    incomplete = replace(
        values["workflow"],
        phase="executing",
    )
    with pytest.raises(
        DurableCompactionProofError,
    ):
        fixture.builder.build(
            workflow=incomplete,
            reservation=values["reservation"],
            certificate=values["certificate"],
            authorization=values["authorization"],
            archive=fixture.archive,
            archive_verification=fixture.archive_verification,
            pruning=values["pruning"],
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_require_rejects_tampered_proof(kind):
    fixture = ProofFixture(kind=kind)
    values = fixture.complete()
    proof = replace(
        values["proof"].proof,
        archive_verification_digest=fp("wrong-verification"),
    )
    signed = SignedDurableCompactionProof(
        proof,
        fixture.proof_signer.sign(
            "shell-ai-durable-compaction-proof",
            proof.digest,
        ),
    )
    with pytest.raises(
        DurableCompactionProofError,
    ):
        fixture.builder.require(
            signed,
            workflow=values["workflow"],
            reservation=values["reservation"],
            certificate=values["certificate"],
            authorization=values["authorization"],
            archive=fixture.archive,
            archive_verification=fixture.archive_verification,
            pruning=values["pruning"],
        )


def test_proof_dataclass_rejects_invalid_schema():
    fixture = ProofFixture()
    values = fixture.complete()
    with pytest.raises(ValueError, match="schema"):
        replace(
            values["proof"].proof,
            schema_version=2,
        )


@pytest.mark.parametrize(
    "field",
    [
        "proof_id",
        "workflow_id",
        "workflow_digest",
        "reservation_id",
        "reservation_digest",
        "certificate_id",
        "certificate_digest",
        "authorization_id",
        "authorization_digest",
        "archive_manifest_digest",
        "pruning_operation_id",
        "pruning_manifest_digest",
        "floor_id",
        "floor_digest",
        "current_root",
        "cutoff_root",
        "previous_floor_root",
        "archive_verification_digest",
    ],
)
def test_proof_dataclass_rejects_bad_digest(field):
    fixture = ProofFixture()
    values = fixture.complete()
    with pytest.raises(ValueError, match="SHA-256"):
        replace(
            values["proof"].proof,
            **{field: "bad"},
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("reservation_generation", 0),
        ("current_sequence", 0),
        ("cutoff_sequence", 0),
        ("delete_count", 0),
        ("deleted_items", 0),
        ("fencing_token", 0),
    ],
)
def test_proof_dataclass_requires_positive_counts(field, value):
    fixture = ProofFixture()
    values = fixture.complete()
    with pytest.raises(ValueError, match="positive"):
        replace(
            values["proof"].proof,
            **{field: value},
        )


def test_proof_dataclass_requires_exact_delete_completion():
    fixture = ProofFixture()
    values = fixture.complete()
    with pytest.raises(ValueError, match="all planned"):
        replace(
            values["proof"].proof,
            deleted_items=values["proof"].proof.deleted_items - 1,
        )


def test_proof_dataclass_rejects_cutoff_above_head():
    fixture = ProofFixture()
    values = fixture.complete()
    proof = values["proof"].proof
    with pytest.raises(ValueError, match="cutoff exceeds"):
        replace(
            proof,
            cutoff_sequence=proof.current_sequence + 1,
            delete_count=proof.current_sequence + 1,
            deleted_items=proof.current_sequence + 1,
        )


def test_proof_dataclass_requires_genesis_root_for_zero_floor():
    fixture = ProofFixture()
    values = fixture.complete()
    with pytest.raises(ValueError, match="genesis"):
        replace(
            values["proof"].proof,
            previous_floor_root=fp("not-genesis"),
        )


def test_proof_dataclass_rejects_issue_before_completion():
    fixture = ProofFixture()
    values = fixture.complete()
    proof = values["proof"].proof
    with pytest.raises(ValueError, match="before"):
        replace(
            proof,
            issued_at=max(0.0, proof.completed_at - 1.0),
        )


def test_signed_proof_requires_correct_types():
    fixture = ProofFixture()
    values = fixture.complete()
    with pytest.raises(TypeError, match="proof"):
        SignedDurableCompactionProof(
            object(),
            values["proof"].signature,
        )
    with pytest.raises(TypeError, match="signature"):
        SignedDurableCompactionProof(
            values["proof"].proof,
            object(),
        )


def test_verification_dataclass_rejects_bad_flags():
    fixture = ProofFixture()
    values = fixture.complete()
    report = fixture.inspect(values)
    with pytest.raises(ValueError, match="bool"):
        replace(
            report,
            archive_valid="yes",
        )


def test_verification_dataclass_rejects_bad_proof_id():
    fixture = ProofFixture()
    values = fixture.complete()
    report = fixture.inspect(values)
    with pytest.raises(ValueError, match="SHA-256"):
        replace(
            report,
            proof_id="bad",
        )


def test_builder_constructor_requires_proof_signer():
    with pytest.raises(TypeError, match="proof_signer"):
        DurableCompactionProofBuilder(object())


@pytest.mark.parametrize(
    "field",
    [
        "certificate_signer",
        "authorization_signer",
        "reservation_signer",
        "archive_signer",
        "floor_signer",
    ],
)
def test_builder_constructor_rejects_wrong_optional_signer(field):
    kwargs = {field: object()}
    with pytest.raises(TypeError, match=field):
        DurableCompactionProofBuilder(
            signer("proof", b"z"),
            **kwargs,
        )


def test_builder_constructor_requires_callable_clock():
    with pytest.raises(TypeError, match="clock"):
        DurableCompactionProofBuilder(
            signer("proof", b"z"),
            clock=object(),
        )


def test_build_rejects_invalid_clock():
    fixture = ProofFixture()
    values = fixture.complete()
    builder = DurableCompactionProofBuilder(
        fixture.proof_signer,
        certificate_signer=fixture.certificate_signer,
        authorization_signer=fixture.authorization_signer,
        reservation_signer=fixture.reservation_signer,
        archive_signer=fixture.archive_signer,
        floor_signer=fixture.floor_signer,
        clock=lambda: float("nan"),
    )
    with pytest.raises(ValueError, match="clock"):
        builder.build(
            workflow=values["workflow"],
            reservation=values["reservation"],
            certificate=values["certificate"],
            authorization=values["authorization"],
            archive=fixture.archive,
            archive_verification=fixture.archive_verification,
            pruning=values["pruning"],
        )
