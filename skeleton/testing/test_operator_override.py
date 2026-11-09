from __future__ import annotations

import pytest

from skeleton.security.operator_override import (
    OperatorOverrideController,
    OperatorOverrideError,
    OverrideAction,
)


def _controller(**kwargs) -> OperatorOverrideController:
    return OperatorOverrideController(**kwargs)


def _grant(controller: OperatorOverrideController, *, now: float = 10.0, max_uses: int = 3):
    return controller.issue_grant(
        operator_id="operator-1",
        scopes=("repair:tenant-a", "restart:worker-a"),
        now=now,
        duration_seconds=120.0,
        max_uses=max_uses,
        reason="recover failed tenant",
    )


def test_break_glass_rejects_wildcard_authority() -> None:
    controller = _controller()
    with pytest.raises(OperatorOverrideError, match="exact"):
        controller.issue_grant(
            operator_id="operator-1",
            scopes=("repair:*",),
            now=1.0,
            duration_seconds=60.0,
            max_uses=1,
            reason="too broad",
        )


def test_break_glass_grant_is_time_bounded_and_scope_bounded() -> None:
    controller = _controller()
    grant = _grant(controller)
    action = OverrideAction("repair", "tenant-a")

    controller.execute(grant.grant_id, action, now=20.0)

    with pytest.raises(OperatorOverrideError, match="scope"):
        controller.execute(
            grant.grant_id,
            OverrideAction("repair", "tenant-b"),
            now=21.0,
        )
    with pytest.raises(OperatorOverrideError, match="currently valid"):
        controller.execute(grant.grant_id, action, now=131.0)


def test_destructive_action_requires_matching_recent_preview() -> None:
    controller = _controller(preview_ttl_seconds=5.0)
    grant = _grant(controller)
    action = OverrideAction(
        "repair",
        "tenant-a",
        destructive=True,
        inverse_action="restore_snapshot",
    )

    with pytest.raises(OperatorOverrideError, match="requires preview"):
        controller.execute(grant.grant_id, action, now=20.0)

    preview = controller.preview(grant.grant_id, action, now=20.0)
    receipt = controller.execute(
        grant.grant_id,
        action,
        now=24.0,
        preview_digest=preview.digest,
    )
    assert receipt.preview_digest == preview.digest
    assert receipt.undo_deadline == 624.0


def test_stale_or_mismatched_preview_fails_closed() -> None:
    controller = _controller(preview_ttl_seconds=5.0)
    grant = _grant(controller)
    action = OverrideAction(
        "repair",
        "tenant-a",
        destructive=True,
        inverse_action="restore",
    )
    preview = controller.preview(grant.grant_id, action, now=20.0)

    with pytest.raises(OperatorOverrideError, match="stale"):
        controller.execute(
            grant.grant_id,
            action,
            now=26.0,
            preview_digest=preview.digest,
        )


def test_approval_fatigue_blocks_repeated_operator_actions() -> None:
    controller = _controller(
        approval_window_seconds=60.0,
        max_approvals_per_window=2,
    )
    grant = _grant(controller, max_uses=4)
    action = OverrideAction("restart", "worker-a")

    controller.execute(grant.grant_id, action, now=20.0)
    controller.execute(grant.grant_id, action, now=21.0)
    with pytest.raises(OperatorOverrideError, match="fatigue"):
        controller.execute(grant.grant_id, action, now=22.0)

    # Window expiry restores operator capacity without changing the grant scope.
    controller.execute(grant.grant_id, action, now=81.1)


def test_grant_use_budget_is_enforced() -> None:
    controller = _controller(max_approvals_per_window=10)
    grant = _grant(controller, max_uses=1)
    action = OverrideAction("restart", "worker-a")

    controller.execute(grant.grant_id, action, now=20.0)
    with pytest.raises(OperatorOverrideError, match="use budget"):
        controller.execute(grant.grant_id, action, now=21.0)


def test_destructive_recovery_has_one_time_bounded_undo() -> None:
    controller = _controller(undo_window_seconds=30.0)
    grant = _grant(controller)
    action = OverrideAction(
        "repair",
        "tenant-a",
        destructive=True,
        inverse_action="restore_snapshot",
    )
    preview = controller.preview(grant.grant_id, action, now=20.0)
    receipt = controller.execute(
        grant.grant_id,
        action,
        now=21.0,
        preview_digest=preview.digest,
    )

    undo = controller.undo(receipt.receipt_id, now=30.0)
    assert undo.kind == "override_undone"

    with pytest.raises(OperatorOverrideError, match="already undone"):
        controller.undo(receipt.receipt_id, now=31.0)


def test_undo_window_expiry_fails_closed() -> None:
    controller = _controller(undo_window_seconds=5.0)
    grant = _grant(controller)
    action = OverrideAction(
        "repair",
        "tenant-a",
        destructive=True,
        inverse_action="restore_snapshot",
    )
    preview = controller.preview(grant.grant_id, action, now=20.0)
    receipt = controller.execute(
        grant.grant_id,
        action,
        now=21.0,
        preview_digest=preview.digest,
    )
    with pytest.raises(OperatorOverrideError, match="expired"):
        controller.undo(receipt.receipt_id, now=27.0)


def test_non_reversible_action_cannot_fake_undo() -> None:
    controller = _controller()
    grant = _grant(controller)
    receipt = controller.execute(
        grant.grant_id,
        OverrideAction("restart", "worker-a"),
        now=20.0,
    )
    with pytest.raises(OperatorOverrideError, match="no undo"):
        controller.undo(receipt.receipt_id, now=21.0)


def test_audit_chain_is_append_only_and_tamper_evident() -> None:
    controller = _controller()
    grant = _grant(controller)
    action = OverrideAction("restart", "worker-a")
    controller.execute(grant.grant_id, action, now=20.0)

    events = controller.audit_events()
    assert [event.kind for event in events] == ["grant_issued", "override_executed"]
    assert events[0].previous_digest == "0" * 64
    assert events[1].previous_digest == events[0].digest
    assert controller.verify_audit_chain() is True
