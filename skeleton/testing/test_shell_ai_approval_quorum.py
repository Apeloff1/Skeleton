"""Distributed dual-control quorum and seal-binding tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.approval_quorum import (
    AIApprovalQuorumStore,
    QuorumApproval,
    QuorumApprovalError,
    QuorumApprovalPolicy,
    QuorumApprovalState,
    QuorumVoteDecision,
)
from skeleton.shells.ai.distributed_seal import DistributedExecutionSealRegistry
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.execution_seal import (
    ExecutionSealAuthority,
    ExecutionSealError,
)
from skeleton.shells.ai.seal_registry import ExecutionSealRegistry
from skeleton.shells.ai.stale_guard import PlanPin


def fp(char):
    return char * 64


def pin():
    return PlanPin(
        fp("a"),
        fp("b"),
        fp("c"),
        fp("d"),
        fp("e"),
        fp("f"),
        fp("1"),
    )


def open_approval(
    store,
    *,
    principal="alice",
    ttl=60,
):
    return store.open(
        principal=principal,
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        ttl_seconds=ttl,
    )


def complete(store, approval_id, approvers=("reviewer-1", "reviewer-2")):
    current = None
    for approver in approvers:
        current = store.vote(
            approval_id,
            approver=approver,
        )
    return current


def test_quorum_policy_defaults_to_two_distinct_votes():
    policy = QuorumApprovalPolicy()
    assert policy.required_votes == 2
    assert policy.max_votes >= 2
    assert policy.forbid_principal_self_approval


@pytest.mark.parametrize(
    "kwargs",
    [
        {"required_votes": 1},
        {"required_votes": 3, "max_votes": 2},
        {"max_votes": 129},
        {"max_ttl_seconds": 0},
    ],
)
def test_quorum_policy_validation(kwargs):
    with pytest.raises(ValueError):
        QuorumApprovalPolicy(**kwargs)


def test_quorum_policy_role_validation():
    with pytest.raises(ValueError):
        QuorumApprovalPolicy(
            allowed_roles=frozenset({""})
        )


def test_quorum_open_revision_one():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    stored = open_approval(store)
    assert stored.revision == 1
    assert stored.approval.principal == "alice"
    assert stored.approval.votes == ()
    assert not stored.approval.complete
    assert not stored.approval.consumed


def test_quorum_open_generates_distinct_ids():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    first = open_approval(store)
    second = open_approval(store)
    assert first.approval.approval_id != second.approval.approval_id


def test_quorum_current_missing_is_none():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    assert store.current("missing") is None


def test_quorum_vote_increments_revision():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    voted = store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
    )
    assert voted.revision == 2
    assert len(voted.approval.votes) == 1
    assert voted.approval.votes[0].approver == "reviewer-1"


def test_quorum_two_distinct_votes_complete():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    complete_record = complete(
        store,
        opened.approval.approval_id,
    )
    assert complete_record.revision == 3
    assert complete_record.approval.complete
    assert {
        item.approver for item in complete_record.approval.votes
    } == {"reviewer-1", "reviewer-2"}


def test_quorum_same_approver_vote_is_idempotent():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    first = store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
        role="security",
    )
    second = store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
        role="security",
    )
    assert first == second
    assert second.revision == 2


def test_quorum_same_approver_role_change_rejected():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
        role="security",
    )
    with pytest.raises(QuorumApprovalError, match="different role"):
        store.vote(
            opened.approval.approval_id,
            approver="reviewer-1",
            role="operator",
        )


def test_quorum_principal_cannot_self_approve_by_default():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store, principal="alice")
    with pytest.raises(QuorumApprovalError, match="own execution"):
        store.vote(
            opened.approval.approval_id,
            approver="alice",
        )


def test_quorum_can_allow_principal_vote_by_policy():
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        policy=QuorumApprovalPolicy(
            forbid_principal_self_approval=False
        ),
    )
    opened = open_approval(store, principal="alice")
    voted = store.vote(
        opened.approval.approval_id,
        approver="alice",
    )
    assert voted.approval.votes[0].approver == "alice"


def test_quorum_allowed_roles_enforced():
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        policy=QuorumApprovalPolicy(
            allowed_roles=frozenset({"security", "operator"})
        ),
    )
    opened = open_approval(store)
    store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
        role="security",
    )
    with pytest.raises(QuorumApprovalError, match="role"):
        store.vote(
            opened.approval.approval_id,
            approver="reviewer-2",
            role="finance",
        )


def test_quorum_vote_capacity():
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        policy=QuorumApprovalPolicy(
            required_votes=2,
            max_votes=2,
        ),
    )
    opened = open_approval(store)
    complete(store, opened.approval.approval_id)
    with pytest.raises(QuorumApprovalError, match="capacity"):
        store.vote(
            opened.approval.approval_id,
            approver="reviewer-3",
        )


def test_quorum_missing_approval_vote_rejected():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    with pytest.raises(QuorumApprovalError, match="does not exist"):
        store.vote(
            "missing",
            approver="reviewer-1",
        )


def test_quorum_require_incomplete_rejected():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    first = store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
    )
    with pytest.raises(QuorumApprovalError, match="enough votes"):
        store.require(
            first.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_require_complete_succeeds():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    finished = complete(
        store,
        opened.approval.approval_id,
    )
    current = store.require(
        finished.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    assert current.complete
    assert current.digest == finished.approval.digest


def test_quorum_require_principal_mismatch():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    finished = complete(
        store,
        open_approval(store).approval.approval_id,
    )
    with pytest.raises(QuorumApprovalError, match="principal"):
        store.require(
            finished.approval,
            principal="bob",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_require_intent_mismatch():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    finished = complete(
        store,
        open_approval(store).approval.approval_id,
    )
    with pytest.raises(QuorumApprovalError, match="intent"):
        store.require(
            finished.approval,
            principal="alice",
            intent_fingerprint=fp("x"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_require_proposal_mismatch():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    finished = complete(
        store,
        open_approval(store).approval.approval_id,
    )
    with pytest.raises(QuorumApprovalError, match="proposal"):
        store.require(
            finished.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("x"),
        )


def test_quorum_stale_evidence_rejected_after_new_vote():
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        policy=QuorumApprovalPolicy(
            required_votes=2,
            max_votes=3,
        ),
    )
    opened = open_approval(store)
    finished = complete(
        store,
        opened.approval.approval_id,
    )
    store.vote(
        opened.approval.approval_id,
        approver="reviewer-3",
    )
    with pytest.raises(QuorumApprovalError, match="stale"):
        store.require(
            finished.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_expired_vote_rejected():
    now = [0.0]
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(clock=lambda: now[0]),
        clock=lambda: now[0],
    )
    opened = open_approval(store, ttl=1)
    now[0] = 1
    with pytest.raises(QuorumApprovalError, match="expired"):
        store.vote(
            opened.approval.approval_id,
            approver="reviewer-1",
        )


def test_quorum_expired_require_rejected():
    now = [0.0]
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(clock=lambda: now[0]),
        clock=lambda: now[0],
    )
    opened = open_approval(store, ttl=1)
    now[0] = 0.1
    finished = complete(
        store,
        opened.approval.approval_id,
    )
    now[0] = 1
    with pytest.raises(QuorumApprovalError, match="expired"):
        store.require(
            finished.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_ttl_max_enforced():
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        policy=QuorumApprovalPolicy(max_ttl_seconds=10),
    )
    with pytest.raises(ValueError, match="TTL"):
        open_approval(store, ttl=11)


def test_quorum_consume_marks_record_consumed():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    finished = complete(
        store,
        open_approval(store).approval.approval_id,
    )
    consumed = store.consume(
        finished.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    assert consumed.consumed
    current = store.current(consumed.approval_id)
    assert current.approval.consumed


def test_quorum_consume_is_single_use():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    finished = complete(
        store,
        open_approval(store).approval.approval_id,
    )
    store.consume(
        finished.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    with pytest.raises(QuorumApprovalError):
        store.consume(
            finished.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_vote_after_consumption_rejected():
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        policy=QuorumApprovalPolicy(max_votes=3),
    )
    finished = complete(
        store,
        open_approval(store).approval.approval_id,
    )
    store.consume(
        finished.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    with pytest.raises(QuorumApprovalError, match="consumed"):
        store.vote(
            finished.approval.approval_id,
            approver="reviewer-3",
        )


def test_quorum_digest_changes_with_vote():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    first = opened.approval.digest
    voted = store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
    )
    assert voted.approval.digest != first


def test_quorum_digest_changes_when_consumed():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    finished = complete(
        store,
        open_approval(store).approval.approval_id,
    )
    consumed = store.consume(
        finished.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    assert consumed.digest != finished.approval.digest


def test_execution_seal_binds_quorum_digest():
    authority = ExecutionSealAuthority(b"k" * 32)
    quorum_digest = fp("q")
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=quorum_digest,
    )
    assert seal.assurance_digest == quorum_digest
    authority.verify(
        seal,
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=quorum_digest,
    )


def test_execution_seal_rejects_quorum_digest_swap():
    authority = ExecutionSealAuthority(b"k" * 32)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    with pytest.raises(ExecutionSealError, match="assurance"):
        authority.verify(
            seal,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
            assurance_digest=fp("x"),
        )


def test_execution_seal_signature_covers_quorum_digest():
    authority = ExecutionSealAuthority(b"k" * 32)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    tampered = replace(
        seal,
        assurance_digest=fp("x"),
    )
    with pytest.raises(ExecutionSealError):
        authority.verify(
            tampered,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
            assurance_digest=fp("x"),
        )


def test_local_seal_registry_requires_matching_quorum_digest():
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    with pytest.raises(ExecutionSealError):
        registry.consume(
            seal,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
            assurance_digest=fp("x"),
        )
    assert not registry.used(seal.seal_id)


def test_local_seal_registry_consumes_with_matching_quorum_digest():
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    registry.consume(
        seal,
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    assert registry.used(seal.seal_id)


def test_distributed_seal_registry_requires_matching_quorum_digest():
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = DistributedExecutionSealRegistry(
        authority,
        InMemoryFencedStore(),
    )
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    with pytest.raises(ExecutionSealError):
        registry.consume(
            seal,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
            assurance_digest=fp("x"),
        )
    assert not registry.used(seal.seal_id)


def test_distributed_seal_registry_consumes_matching_quorum_digest():
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = DistributedExecutionSealRegistry(
        authority,
        InMemoryFencedStore(),
    )
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    registry.consume(
        seal,
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        assurance_digest=fp("q"),
    )
    assert registry.used(seal.seal_id)


def test_quorum_reject_vote_is_terminal():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    rejected = store.reject(
        opened.approval.approval_id,
        approver="security-reviewer",
        reason="unsafe side effect",
    )
    assert rejected.approval.policy_rejected
    assert rejected.approval.state_at(rejected.approval.created_at) is QuorumApprovalState.REJECTED
    assert rejected.approval.votes[0].decision is QuorumVoteDecision.REJECT
    assert rejected.approval.votes[0].reason == "unsafe side effect"


def test_quorum_rejected_cannot_receive_more_votes():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    store.reject(
        opened.approval.approval_id,
        approver="security-reviewer",
    )
    with pytest.raises(QuorumApprovalError, match="rejected"):
        store.vote(
            opened.approval.approval_id,
            approver="operator-reviewer",
        )


def test_quorum_rejected_cannot_be_required():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    rejected = store.reject(
        opened.approval.approval_id,
        approver="security-reviewer",
    )
    with pytest.raises(QuorumApprovalError, match="rejected"):
        store.require(
            rejected.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_rejected_cannot_be_consumed():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    rejected = store.reject(
        opened.approval.approval_id,
        approver="security-reviewer",
    )
    with pytest.raises(QuorumApprovalError, match="rejected"):
        store.consume(
            rejected.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_approver_cannot_change_vote_decision():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
        role="security",
        decision=QuorumVoteDecision.APPROVE,
    )
    with pytest.raises(QuorumApprovalError, match="change"):
        store.vote(
            opened.approval.approval_id,
            approver="reviewer-1",
            role="security",
            decision=QuorumVoteDecision.REJECT,
        )


def test_quorum_reject_digest_differs_from_approve_digest():
    approve_store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        clock=lambda: 100.0,
    )
    reject_store = AIApprovalQuorumStore(
        InMemoryFencedStore(),
        clock=lambda: 100.0,
    )
    approved = approve_store.open(
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    rejected = reject_store.open(
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    approved = approve_store.vote(
        approved.approval.approval_id,
        approver="reviewer",
    )
    rejected = reject_store.reject(
        rejected.approval.approval_id,
        approver="reviewer",
    )
    assert approved.approval.digest != rejected.approval.digest


def test_quorum_metadata_is_immutable_and_in_digest():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    first = store.open(
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        metadata={"change_ticket": "CR-42"},
    )
    second = store.open(
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        metadata={"change_ticket": "CR-43"},
    )
    with pytest.raises(TypeError):
        first.approval.metadata["change_ticket"] = "tampered"
    assert first.approval.digest != second.approval.digest


def test_quorum_metadata_field_limit():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    with pytest.raises(ValueError, match="metadata"):
        store.open(
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
            metadata={str(index): "x" for index in range(65)},
        )


def test_quorum_reject_reason_limit():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    with pytest.raises(ValueError, match="reason"):
        store.reject(
            opened.approval.approval_id,
            approver="reviewer",
            reason="x" * 2049,
        )


def test_quorum_state_progression_pending_approved_consumed():
    now = [0.0]
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(clock=lambda: now[0]),
        clock=lambda: now[0],
    )
    opened = open_approval(store, ttl=100)
    assert opened.approval.state_at(now[0]) is QuorumApprovalState.PENDING
    first = store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
    )
    assert first.approval.state_at(now[0]) is QuorumApprovalState.PENDING
    second = store.vote(
        opened.approval.approval_id,
        approver="reviewer-2",
    )
    assert second.approval.state_at(now[0]) is QuorumApprovalState.APPROVED
    consumed = store.consume(
        second.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    assert consumed.state_at(now[0]) is QuorumApprovalState.CONSUMED


def test_quorum_state_expired():
    now = [0.0]
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(clock=lambda: now[0]),
        clock=lambda: now[0],
    )
    opened = open_approval(store, ttl=1)
    now[0] = 1
    assert opened.approval.state_at(now[0]) is QuorumApprovalState.EXPIRED


def test_quorum_reject_vote_vetoes_approval():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    rejected = store.reject(
        opened.approval.approval_id,
        approver="security-reviewer",
        reason="unsafe side effect",
    )
    assert rejected.approval.policy_rejected
    assert not rejected.approval.complete
    with pytest.raises(QuorumApprovalError, match="rejected"):
        store.vote(
            opened.approval.approval_id,
            approver="operator",
        )


def test_quorum_rejected_evidence_cannot_require():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    rejected = store.reject(
        opened.approval.approval_id,
        approver="security-reviewer",
        reason="source drift",
    )
    with pytest.raises(QuorumApprovalError, match="rejected"):
        store.require(
            rejected.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_rejected_evidence_cannot_consume():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    rejected = store.reject(
        opened.approval.approval_id,
        approver="security-reviewer",
    )
    with pytest.raises(QuorumApprovalError, match="rejected"):
        store.consume(
            rejected.approval,
            principal="alice",
            intent_fingerprint=fp("i"),
            proposal_fingerprint=fp("p"),
        )


def test_quorum_approver_cannot_change_approve_to_reject():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
    )
    with pytest.raises(QuorumApprovalError, match="change"):
        store.reject(
            opened.approval.approval_id,
            approver="reviewer-1",
        )


def test_quorum_approver_cannot_change_reject_to_approve():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = open_approval(store)
    store.reject(
        opened.approval.approval_id,
        approver="reviewer-1",
    )
    # Rejected quorum is terminal for subsequent vote operations.
    with pytest.raises(QuorumApprovalError, match="rejected"):
        store.vote(
            opened.approval.approval_id,
            approver="reviewer-1",
        )


def test_quorum_reject_reason_is_bound_into_digest():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    first = open_approval(store)
    second = open_approval(store)
    first_rejected = store.reject(
        first.approval.approval_id,
        approver="security",
        reason="reason one",
    )
    second_rejected = store.reject(
        second.approval.approval_id,
        approver="security",
        reason="reason two",
    )
    assert (
        first_rejected.approval.votes[0].reason
        == "reason one"
    )
    assert (
        second_rejected.approval.votes[0].reason
        == "reason two"
    )
    assert first_rejected.approval.digest != second_rejected.approval.digest


def test_quorum_metadata_is_immutable():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = store.open(
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        metadata={"ticket": "SEC-42"},
    )
    assert opened.approval.metadata["ticket"] == "SEC-42"
    with pytest.raises(TypeError):
        opened.approval.metadata["ticket"] = "changed"


def test_quorum_metadata_survives_votes_and_consumption():
    store = AIApprovalQuorumStore(InMemoryFencedStore())
    opened = store.open(
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        metadata={"change": "CHG-1"},
    )
    first = store.vote(
        opened.approval.approval_id,
        approver="reviewer-1",
    )
    second = store.vote(
        opened.approval.approval_id,
        approver="reviewer-2",
    )
    consumed = store.consume(
        second.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    assert first.approval.metadata["change"] == "CHG-1"
    assert second.approval.metadata["change"] == "CHG-1"
    assert consumed.metadata["change"] == "CHG-1"


def test_quorum_state_pending_approved_rejected_consumed_expired():
    from skeleton.shells.ai.approval_quorum import QuorumApprovalState

    now = [0.0]
    store = AIApprovalQuorumStore(
        InMemoryFencedStore(clock=lambda: now[0]),
        clock=lambda: now[0],
    )
    pending = open_approval(store, ttl=10)
    assert pending.approval.state_at(now[0]) is QuorumApprovalState.PENDING
    store.vote(pending.approval.approval_id, approver="one")
    approved = store.vote(
        pending.approval.approval_id,
        approver="two",
    )
    assert approved.approval.state_at(now[0]) is QuorumApprovalState.APPROVED
    consumed = store.consume(
        approved.approval,
        principal="alice",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
    )
    assert consumed.state_at(now[0]) is QuorumApprovalState.CONSUMED

    rejected_open = open_approval(store, ttl=10)
    rejected = store.reject(
        rejected_open.approval.approval_id,
        approver="security",
    )
    assert rejected.approval.state_at(now[0]) is QuorumApprovalState.REJECTED

    expiring = open_approval(store, ttl=1)
    now[0] = 1
    assert expiring.approval.state_at(now[0]) is QuorumApprovalState.EXPIRED
