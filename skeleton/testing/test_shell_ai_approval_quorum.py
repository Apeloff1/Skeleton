"""Distributed dual-control quorum and seal-binding tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.approval_quorum import (
    AIApprovalQuorumStore,
    QuorumApproval,
    QuorumApprovalError,
    QuorumApprovalPolicy,
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
