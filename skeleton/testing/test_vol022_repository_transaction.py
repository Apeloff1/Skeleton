from __future__ import annotations

from hashlib import sha256

import pytest

from skeleton.automation.independent_review import review_workspace
from skeleton.automation.repository_transaction import (
    MutationPhase,
    RepositoryMutationTransaction,
)
from skeleton.automation.transactional_workspace import (
    EditLeaseRegistry,
    TransactionalWorkspace,
    WorkspaceError,
)


def d(value: bytes) -> str:
    return sha256(value).hexdigest()


def evidence(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def _edited_transaction():
    registry = EditLeaseRegistry()
    workspace = TransactionalWorkspace({"a": b"old"}, lease_registry=registry)
    tx = RepositoryMutationTransaction(transaction_id="tx-1", proposer_id="builder")
    tx.record_inspection(base_digest=workspace.base_digest, evidence_digest=evidence("inspect"))
    tx.record_plan(planned_paths=("a",))
    lease = workspace.acquire_lease(
        lease_id="lease-1",
        owner_id="builder",
        paths=("a",),
    )
    tx.bind_lease(lease)
    workspace.write_leased(lease, "a", b"new", expected_digest=d(b"old"))
    receipt = workspace.commit_leased(lease)
    patch = tx.record_edit(receipt)
    return tx, receipt, patch


def test_repository_mutation_flow_enforces_full_order_and_exact_patch_review():
    tx, receipt, patch = _edited_transaction()
    assert patch.rollback_base_digest == receipt.base_digest
    assert patch.changed_paths == ("a",)
    tx.record_build(evidence_digest=evidence("build"), success=True)
    tx.record_test(evidence_digest=evidence("test"), success=True)
    review = review_workspace(
        receipt,
        proposer_id="builder",
        reviewer_id="independent-verifier",
        decision="approve",
    )
    tx.record_review(review)
    tx.record_verification(evidence_digest=evidence("verify"), success=True)
    assert tx.phase is MutationPhase.COMPLETE
    assert len(tx.completion_digest) == 64
    assert [item.phase for item in tx.evidence] == [
        MutationPhase.INSPECT,
        MutationPhase.PLAN,
        MutationPhase.LEASE,
        MutationPhase.EDIT,
        MutationPhase.BUILD,
        MutationPhase.TEST,
        MutationPhase.REVIEW,
        MutationPhase.VERIFY,
    ]


def test_repository_mutation_flow_rejects_out_of_order_progression():
    tx = RepositoryMutationTransaction(transaction_id="tx", proposer_id="builder")
    with pytest.raises(WorkspaceError, match="phase mismatch"):
        tx.record_plan(planned_paths=("a",))


def test_repository_mutation_flow_requires_exact_plan_lease_paths():
    registry = EditLeaseRegistry()
    workspace = TransactionalWorkspace({"a": b"x", "b": b"y"}, lease_registry=registry)
    tx = RepositoryMutationTransaction(transaction_id="tx", proposer_id="builder")
    tx.record_inspection(base_digest=workspace.base_digest, evidence_digest=evidence("inspect"))
    tx.record_plan(planned_paths=("a",))
    lease = registry.acquire(
        lease_id="lease",
        owner_id="builder",
        base_digest=workspace.base_digest,
        paths=("b",),
    )
    with pytest.raises(WorkspaceError, match="paths must exactly match"):
        tx.bind_lease(lease)


def test_failed_build_fails_closed_before_test_or_review():
    tx, _, _ = _edited_transaction()
    tx.record_build(evidence_digest=evidence("build-fail"), success=False)
    assert tx.phase is MutationPhase.FAILED
    with pytest.raises(WorkspaceError, match="phase mismatch"):
        tx.record_test(evidence_digest=evidence("test"), success=True)


def test_review_for_different_patch_cannot_advance_transaction():
    tx, _, _ = _edited_transaction()
    tx.record_build(evidence_digest=evidence("build"), success=True)
    tx.record_test(evidence_digest=evidence("test"), success=True)

    other = TransactionalWorkspace({"a": b"other"})
    other_receipt = other.commit()
    review = review_workspace(
        other_receipt,
        proposer_id="builder",
        reviewer_id="independent-verifier",
        decision="approve",
    )
    with pytest.raises(WorkspaceError, match="did not approve exact patch"):
        tx.record_review(review)
    assert tx.phase is MutationPhase.FAILED


def test_failed_final_verification_never_produces_completion_digest():
    tx, receipt, _ = _edited_transaction()
    tx.record_build(evidence_digest=evidence("build"), success=True)
    tx.record_test(evidence_digest=evidence("test"), success=True)
    tx.record_review(
        review_workspace(
            receipt,
            proposer_id="builder",
            reviewer_id="independent-verifier",
            decision="approve",
        )
    )
    tx.record_verification(evidence_digest=evidence("verify-fail"), success=False)
    assert tx.phase is MutationPhase.FAILED
    with pytest.raises(WorkspaceError, match="not complete"):
        _ = tx.completion_digest
