from __future__ import annotations

import hashlib

import pytest

from skeleton.shells.ai.approval_quorum import (
    QuorumApproval,
    QuorumVote,
    QuorumVoteDecision,
)
from skeleton.shells.break_glass import BreakGlassController, BreakGlassError


ACTION = hashlib.sha256(b"emergency-action").hexdigest()
INTENT = hashlib.sha256(b"emergency-intent").hexdigest()


def approval(*, principal: str = "operator", expires_at: float = 1000.0) -> QuorumApproval:
    return QuorumApproval(
        approval_id="approval-1",
        principal=principal,
        intent_fingerprint=INTENT,
        proposal_fingerprint=ACTION,
        required_votes=2,
        votes=(
            QuorumVote("reviewer-a", "sre", 10.0, QuorumVoteDecision.APPROVE),
            QuorumVote("reviewer-b", "security", 11.0, QuorumVoteDecision.APPROVE),
        ),
        created_at=1.0,
        expires_at=expires_at,
    )


def test_break_glass_requires_completed_dual_control_and_exact_action() -> None:
    controller = BreakGlassController(clock=lambda: 100.0)
    grant = controller.issue(
        approval=approval(),
        principal="operator",
        action_digest=ACTION,
        reason="restore control plane",
    )
    controller.authorize(
        grant,
        principal="operator",
        action_digest=ACTION,
    )
    assert grant.approval_digest == approval().digest
    assert len(grant.undo_token) == 64


def test_operator_error_wrong_principal_and_action_fail_closed() -> None:
    controller = BreakGlassController(clock=lambda: 100.0)

    with pytest.raises(BreakGlassError, match="principal mismatch"):
        controller.issue(
            approval=approval(),
            principal="other",
            action_digest=ACTION,
            reason="operator mistake",
        )

    with pytest.raises(BreakGlassError, match="action mismatch"):
        controller.issue(
            approval=approval(),
            principal="operator",
            action_digest="0" * 64,
            reason="wrong action",
        )


def test_approval_fatigue_budget_blocks_emergency_spam() -> None:
    now = [100.0]
    controller = BreakGlassController(
        max_grants_per_window=2,
        window_seconds=60.0,
        clock=lambda: now[0],
    )

    controller.issue(
        approval=approval(),
        principal="operator",
        action_digest=ACTION,
        reason="first",
    )
    now[0] = 101.0
    controller.issue(
        approval=approval(),
        principal="operator",
        action_digest=ACTION,
        reason="second",
    )
    now[0] = 102.0
    with pytest.raises(BreakGlassError, match="fatigue budget exhausted"):
        controller.issue(
            approval=approval(),
            principal="operator",
            action_digest=ACTION,
            reason="third",
        )

    now[0] = 161.0
    controller.issue(
        approval=approval(expires_at=1000.0),
        principal="operator",
        action_digest=ACTION,
        reason="after window",
    )


def test_undo_is_one_shot_and_revokes_future_authorization() -> None:
    controller = BreakGlassController(clock=lambda: 100.0)
    grant = controller.issue(
        approval=approval(),
        principal="operator",
        action_digest=ACTION,
        reason="emergency",
    )
    receipt = controller.undo(grant, undo_token=grant.undo_token)

    assert receipt.grant_id == grant.grant_id
    assert len(receipt.receipt_digest) == 64
    with pytest.raises(BreakGlassError, match="was undone"):
        controller.authorize(
            grant,
            principal="operator",
            action_digest=ACTION,
        )
    with pytest.raises(BreakGlassError, match="already consumed"):
        controller.undo(grant, undo_token=grant.undo_token)


def test_bad_undo_token_does_not_consume_recovery_path() -> None:
    controller = BreakGlassController(clock=lambda: 100.0)
    grant = controller.issue(
        approval=approval(),
        principal="operator",
        action_digest=ACTION,
        reason="emergency",
    )

    with pytest.raises(BreakGlassError, match="token mismatch"):
        controller.undo(grant, undo_token="f" * 64)

    controller.authorize(
        grant,
        principal="operator",
        action_digest=ACTION,
    )
    controller.undo(grant, undo_token=grant.undo_token)


def test_incomplete_rejected_expired_and_consumed_approvals_block() -> None:
    base = approval()
    controller = BreakGlassController(clock=lambda: 100.0)

    incomplete = QuorumApproval(
        **{
            **base.__dict__,
            "votes": (base.votes[0],),
        }
    )
    with pytest.raises(BreakGlassError, match="not complete"):
        controller.issue(
            approval=incomplete,
            principal="operator",
            action_digest=ACTION,
            reason="bad",
        )

    rejected = QuorumApproval(
        **{
            **base.__dict__,
            "votes": (
                base.votes[0],
                QuorumVote(
                    "reviewer-b",
                    "security",
                    11.0,
                    QuorumVoteDecision.REJECT,
                ),
            ),
        }
    )
    with pytest.raises(BreakGlassError, match="not complete"):
        controller.issue(
            approval=rejected,
            principal="operator",
            action_digest=ACTION,
            reason="bad",
        )

    with pytest.raises(BreakGlassError, match="expired"):
        controller.issue(
            approval=approval(expires_at=50.0),
            principal="operator",
            action_digest=ACTION,
            reason="bad",
        )

    consumed = QuorumApproval(
        **{
            **base.__dict__,
            "consumed": True,
        }
    )
    with pytest.raises(BreakGlassError, match="already consumed"):
        controller.issue(
            approval=consumed,
            principal="operator",
            action_digest=ACTION,
            reason="bad",
        )
