"""Regression coverage for B017 human approval boundaries."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from skeleton.forge.creator.approval_boundary import (
    HIGH_IMPACT_ACTIONS,
    ROUTINE_ACTIONS,
    ApprovalBoundaryError,
    approval_required,
    authorize_action,
    create_approval_checkpoint,
    record_human_decision,
    serialize_checkpoint,
    serialize_decision,
    validate_authorization,
    validate_checkpoint,
    validate_decision,
)
from skeleton.forge.creator.work_leases import (
    claim_work,
    empty_lease_state,
    release_lease,
    renew_lease,
)
from skeleton.repo_intelligence.batch_plan import load_plan


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def plan():
    return load_plan()


def _state_with_lease(
    plan,
    *,
    lease_id: str = "lease-approval",
    owner_id: str = "agent-builder",
    now: int = 100,
    ttl: int = 300,
):
    state = empty_lease_state(plan=plan, logical_time=now)
    state, lease = claim_work(
        state,
        lease_id=lease_id,
        owner_id=owner_id,
        batch_ids=("B017",),
        paths=("skeleton/forge/creator",),
        now=now,
        ttl_seconds=ttl,
        plan=plan,
        expected_state_digest=state.digest,
    )
    return state, lease


def _checkpoint(
    plan,
    state,
    *,
    action_kind: str = "publish_release",
    action_id: str = "publish-alpha",
    requester_id: str = "agent-builder",
    lease_id: str = "lease-approval",
    now: int = 110,
    ttl: int = 120,
    payload: str = "proposal-v1",
    evidence=(),
):
    return create_approval_checkpoint(
        state,
        lease_id=lease_id,
        requester_id=requester_id,
        action_id=action_id,
        action_kind=action_kind,
        payload_digest=_digest(payload),
        evidence_digests=evidence,
        now=now,
        ttl_seconds=ttl,
        plan=plan,
    )


def _approval(checkpoint, *, now: int = 120, decision: str = "approve"):
    return record_human_decision(
        checkpoint,
        approver_id="human-reviewer",
        decision=decision,
        now=now,
        evidence_digests=(_digest("review-report"),),
        rationale="Reviewed exact proposed action and supporting evidence.",
    )


@pytest.mark.parametrize("kind", sorted(HIGH_IMPACT_ACTIONS))
def test_high_impact_actions_have_fixed_human_requirement(kind: str) -> None:
    assert approval_required(kind) is True


@pytest.mark.parametrize("kind", sorted(ROUTINE_ACTIONS))
def test_routine_actions_do_not_require_human_checkpoint(kind: str) -> None:
    assert approval_required(kind) is False


def test_unknown_action_kind_fails_closed() -> None:
    with pytest.raises(ApprovalBoundaryError) as caught:
        approval_required("caller-invented-low-risk")
    assert caught.value.context["reason"] == "unknown_action_kind"


def test_checkpoint_binds_exact_lease_payload_and_evidence(plan) -> None:
    state, lease = _state_with_lease(plan)
    checkpoint = _checkpoint(
        plan,
        state,
        evidence=(_digest("b"), _digest("a")),
    )

    assert checkpoint.lease_id == lease.lease_id
    assert checkpoint.lease_revision == lease.revision
    assert checkpoint.lease_digest == lease.digest
    assert checkpoint.batch_ids == lease.scope.batch_ids
    assert checkpoint.paths == lease.scope.paths
    assert checkpoint.payload_digest == _digest("proposal-v1")
    assert checkpoint.evidence_digests == tuple(sorted((_digest("a"), _digest("b"))))
    assert checkpoint.requires_human is True
    assert len(checkpoint.checkpoint_id) == 64
    assert len(checkpoint.digest) == 64
    validate_checkpoint(checkpoint)


def test_checkpoint_evidence_order_is_deterministic(plan) -> None:
    state, _ = _state_with_lease(plan)
    first = _checkpoint(
        plan,
        state,
        evidence=(_digest("z"), _digest("a")),
    )
    second = _checkpoint(
        plan,
        state,
        evidence=(_digest("a"), _digest("z")),
    )
    assert first == second


def test_checkpoint_cannot_outlive_work_lease(plan) -> None:
    state, lease = _state_with_lease(plan, now=100, ttl=20)
    checkpoint = _checkpoint(plan, state, now=105, ttl=10_000)

    assert checkpoint.expires_at == lease.expires_at == 120


def test_wrong_requester_cannot_create_checkpoint(plan) -> None:
    state, _ = _state_with_lease(plan)

    with pytest.raises(ApprovalBoundaryError) as caught:
        _checkpoint(plan, state, requester_id="agent-other")
    assert caught.value.context["reason"] == "lease_owner_mismatch"


def test_high_impact_action_requires_separate_human_approval(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)

    with pytest.raises(ApprovalBoundaryError) as caught:
        authorize_action(
            checkpoint,
            state,
            now=120,
            payload_digest=checkpoint.payload_digest,
            plan=plan,
        )
    assert caught.value.context["reason"] == "approval_required"


def test_requester_cannot_self_approve(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)

    with pytest.raises(ApprovalBoundaryError) as caught:
        record_human_decision(
            checkpoint,
            approver_id=checkpoint.requester_id,
            decision="approve",
            now=120,
            rationale="Self approval must never be accepted.",
        )
    assert caught.value.context["reason"] == "self_approval"


def test_human_approval_records_identity_evidence_and_rationale(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)

    assert decision.checkpoint_digest == checkpoint.digest
    assert decision.approver_id == "human-reviewer"
    assert decision.approver_type == "human"
    assert decision.decision == "approve"
    assert decision.evidence_digests == (_digest("review-report"),)
    assert decision.rationale
    assert len(decision.digest) == 64
    validate_decision(decision, checkpoint)


def test_approved_high_impact_action_authorizes_exact_payload(plan) -> None:
    state, lease = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)

    authorization = authorize_action(
        checkpoint,
        state,
        now=130,
        payload_digest=checkpoint.payload_digest,
        decision=decision,
        plan=plan,
    )

    assert authorization.checkpoint_digest == checkpoint.digest
    assert authorization.decision_digest == decision.digest
    assert authorization.lease_digest == lease.digest
    assert authorization.payload_digest == checkpoint.payload_digest
    assert len(authorization.digest) == 64
    validate_authorization(
        authorization,
        checkpoint,
        state,
        now=130,
        payload_digest=checkpoint.payload_digest,
        decision=decision,
        plan=plan,
    )


def test_payload_substitution_after_approval_is_rejected(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)

    with pytest.raises(ApprovalBoundaryError) as caught:
        authorize_action(
            checkpoint,
            state,
            now=130,
            payload_digest=_digest("different-payload"),
            decision=decision,
            plan=plan,
        )
    assert caught.value.context["reason"] == "payload_mismatch"


def test_denied_action_never_authorizes(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint, decision="deny")

    with pytest.raises(ApprovalBoundaryError) as caught:
        authorize_action(
            checkpoint,
            state,
            now=130,
            payload_digest=checkpoint.payload_digest,
            decision=decision,
            plan=plan,
        )
    assert caught.value.context["reason"] == "approval_denied"


def test_routine_action_authorizes_without_human_decision(plan) -> None:
    state, lease = _state_with_lease(plan)
    checkpoint = _checkpoint(
        plan,
        state,
        action_kind="run_tests",
        action_id="run-test-suite",
    )
    assert checkpoint.requires_human is False

    authorization = authorize_action(
        checkpoint,
        state,
        now=120,
        payload_digest=checkpoint.payload_digest,
        plan=plan,
    )

    assert authorization.decision_digest is None
    assert authorization.lease_digest == lease.digest


def test_routine_action_rejects_unrelated_decision(plan) -> None:
    state, _ = _state_with_lease(plan)
    routine = _checkpoint(
        plan,
        state,
        action_kind="preview",
        action_id="preview-scene",
    )
    high = _checkpoint(
        plan,
        state,
        action_kind="publish_release",
        action_id="publish-scene",
    )
    decision = _approval(high)

    with pytest.raises(ApprovalBoundaryError):
        authorize_action(
            routine,
            state,
            now=130,
            payload_digest=routine.payload_digest,
            decision=decision,
            plan=plan,
        )


def test_lease_renewal_invalidates_prior_checkpoint(plan) -> None:
    state, lease = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)

    renewed_state, renewed = renew_lease(
        state,
        lease_id=lease.lease_id,
        owner_id=lease.owner_id,
        now=125,
        ttl_seconds=300,
        expected_revision=lease.revision,
        plan=plan,
        expected_state_digest=state.digest,
    )
    assert renewed.revision == lease.revision + 1

    with pytest.raises(ApprovalBoundaryError) as caught:
        authorize_action(
            checkpoint,
            renewed_state,
            now=130,
            payload_digest=checkpoint.payload_digest,
            decision=decision,
            plan=plan,
        )
    assert caught.value.context["reason"] == "lease_changed"


def test_lease_release_invalidates_prior_checkpoint(plan) -> None:
    state, lease = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)
    released = release_lease(
        state,
        lease_id=lease.lease_id,
        owner_id=lease.owner_id,
        now=125,
        expected_revision=lease.revision,
        plan=plan,
        expected_state_digest=state.digest,
    )

    with pytest.raises(ApprovalBoundaryError) as caught:
        authorize_action(
            checkpoint,
            released,
            now=130,
            payload_digest=checkpoint.payload_digest,
            decision=decision,
            plan=plan,
        )
    assert caught.value.context["reason"] == "lease_unavailable"


def test_checkpoint_expiry_invalidates_approval(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state, now=110, ttl=10)
    decision = _approval(checkpoint, now=115)

    with pytest.raises(ApprovalBoundaryError) as caught:
        authorize_action(
            checkpoint,
            state,
            now=120,
            payload_digest=checkpoint.payload_digest,
            decision=decision,
            plan=plan,
        )
    assert caught.value.context["reason"] == "checkpoint_expired"


def test_decision_cannot_predate_or_follow_checkpoint_lifetime(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state, now=110, ttl=10)

    with pytest.raises(ApprovalBoundaryError) as caught:
        _approval(checkpoint, now=109)
    assert caught.value.context["reason"] == "time_regression"

    with pytest.raises(ApprovalBoundaryError) as caught:
        _approval(checkpoint, now=120)
    assert caught.value.context["reason"] == "checkpoint_expired"


def test_decision_from_other_checkpoint_is_rejected(plan) -> None:
    state, _ = _state_with_lease(plan)
    first = _checkpoint(plan, state, action_id="publish-one", payload="one")
    second = _checkpoint(plan, state, action_id="publish-two", payload="two")
    decision = _approval(first)

    with pytest.raises(ApprovalBoundaryError) as caught:
        validate_decision(decision, second)
    assert caught.value.context["reason"] == "checkpoint_mismatch"


def test_tampered_checkpoint_requirement_and_digest_fail_closed(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)

    with pytest.raises(ApprovalBoundaryError) as caught:
        validate_checkpoint(replace(checkpoint, requires_human=False))
    assert caught.value.context["reason"] == "derived_field_drift"

    with pytest.raises(ApprovalBoundaryError) as caught:
        validate_checkpoint(replace(checkpoint, digest="0" * 64))
    assert caught.value.context["reason"] == "digest_mismatch"


def test_tampered_decision_digest_and_approver_type_fail_closed(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)

    with pytest.raises(ApprovalBoundaryError) as caught:
        validate_decision(replace(decision, digest="0" * 64), checkpoint)
    assert caught.value.context["reason"] == "digest_mismatch"

    with pytest.raises(ApprovalBoundaryError) as caught:
        validate_decision(replace(decision, approver_type="agent"), checkpoint)
    assert caught.value.context["reason"] == "approver_type"


def test_future_decision_cannot_authorize_earlier_action(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint, now=140)

    with pytest.raises(ApprovalBoundaryError) as caught:
        authorize_action(
            checkpoint,
            state,
            now=130,
            payload_digest=checkpoint.payload_digest,
            decision=decision,
            plan=plan,
        )
    assert caught.value.context["reason"] == "time_regression"


def test_authorization_is_independently_recomputed(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)
    authorization = authorize_action(
        checkpoint,
        state,
        now=130,
        payload_digest=checkpoint.payload_digest,
        decision=decision,
        plan=plan,
    )

    with pytest.raises(ApprovalBoundaryError) as caught:
        validate_authorization(
            replace(authorization, digest="0" * 64),
            checkpoint,
            state,
            now=130,
            payload_digest=checkpoint.payload_digest,
            decision=decision,
            plan=plan,
        )
    assert caught.value.context["reason"] == "digest_mismatch"


def test_checkpoint_and_decision_serialization_are_canonical(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)

    checkpoint_raw = serialize_checkpoint(checkpoint)
    decision_raw = serialize_decision(decision, checkpoint)

    assert checkpoint_raw == json.dumps(
        json.loads(checkpoint_raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert decision_raw == json.dumps(
        json.loads(decision_raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_duplicate_evidence_and_empty_rationale_fail_closed(plan) -> None:
    state, _ = _state_with_lease(plan)
    duplicate = _digest("duplicate")
    with pytest.raises(ApprovalBoundaryError) as caught:
        _checkpoint(plan, state, evidence=(duplicate, duplicate))
    assert caught.value.context["reason"] == "duplicate"

    checkpoint = _checkpoint(plan, state)
    with pytest.raises(ApprovalBoundaryError):
        record_human_decision(
            checkpoint,
            approver_id="human-reviewer",
            decision="approve",
            now=120,
            rationale="",
        )


def test_checkpoint_scope_is_exactly_the_bound_lease_scope(plan) -> None:
    state, _ = _state_with_lease(plan)
    checkpoint = _checkpoint(plan, state)
    decision = _approval(checkpoint)

    forged = replace(
        checkpoint,
        paths=("different/scope",),
    )
    with pytest.raises(ApprovalBoundaryError):
        authorize_action(
            forged,
            state,
            now=130,
            payload_digest=checkpoint.payload_digest,
            decision=decision,
            plan=plan,
        )
