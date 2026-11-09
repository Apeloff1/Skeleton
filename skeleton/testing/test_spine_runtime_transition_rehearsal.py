from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_runtime_transition_rehearsal import (
    SpineRuntimeTransitionRehearsal,
    SpineRuntimeTransitionRehearsalError,
)
from skeleton.persistence.spine_runtime_transition_rehearsal_verify import (
    SpineRuntimeTransitionRehearsalVerify,
    SpineRuntimeTransitionRehearsalVerifyError,
)


NOW = datetime(2026, 10, 1, 16, 45, tzinfo=timezone.utc)


class _Runtime:
    dispatcher_running = False

    def start_dispatcher(self) -> None:
        raise AssertionError("transition rehearsal must not start dispatcher")


def _handoff() -> dict[str, object]:
    return {
        "kind": "spine_runtime_activation_handoff",
        "digest": "h" * 64,
        "boundary_digest": "b" * 64,
        "deployment_id": "p2-runtime-deployment-001",
        "handoff_nonce": "n" * 64,
        "target_driver": "pymongo-async",
        "handoff_expires_at": (NOW + timedelta(minutes=2)).isoformat(),
        "deployment_receipt_authenticated": True,
        "handoff_ready": True,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "dispatcher_running": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def _handoff_verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_activation_handoff_verify",
        "handoff_digest": "h" * 64,
        "boundary_digest": "b" * 64,
        "verified": True,
        "handoff_ready": True,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "dispatcher_running": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def test_deployment_transition_rehearsal_never_executes_transition() -> None:
    card = SpineRuntimeTransitionRehearsal().rehearse(
        handoff=_handoff(),
        handoff_verify=_handoff_verify(),
        runtime=_Runtime(),
        epoch_before=9,
        epoch_after=9,
        now=NOW,
    )
    verified = SpineRuntimeTransitionRehearsalVerify().verify(card)

    assert card["transition_rehearsed"] is True
    assert card["transition_attempted"] is False
    assert card["transition_executed"] is False
    assert card["dispatcher_running"] is False
    assert card["fence_moved"] is False
    assert card["runtime_activated"] is False
    assert verified["verified"] is True


def test_transition_rehearsal_fails_closed_on_expired_handoff_or_running_dispatcher() -> None:
    expired = _handoff()
    expired["handoff_expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(SpineRuntimeTransitionRehearsalError, match="expired"):
        SpineRuntimeTransitionRehearsal().rehearse(
            handoff=expired,
            handoff_verify=_handoff_verify(),
            runtime=_Runtime(),
            epoch_before=9,
            epoch_after=9,
            now=NOW,
        )

    runtime = _Runtime()
    runtime.dispatcher_running = True
    with pytest.raises(SpineRuntimeTransitionRehearsalError, match="dispatcher is running"):
        SpineRuntimeTransitionRehearsal().rehearse(
            handoff=_handoff(),
            handoff_verify=_handoff_verify(),
            runtime=runtime,
            epoch_before=9,
            epoch_after=9,
            now=NOW,
        )


def test_transition_rehearsal_verifier_rejects_execution_or_tamper() -> None:
    card = SpineRuntimeTransitionRehearsal().rehearse(
        handoff=_handoff(),
        handoff_verify=_handoff_verify(),
        runtime=_Runtime(),
        epoch_before=9,
        epoch_after=9,
        now=NOW,
    )

    executed = copy.deepcopy(card)
    executed["transition_executed"] = True
    with pytest.raises(
        SpineRuntimeTransitionRehearsalVerifyError,
        match="executed during rehearsal",
    ):
        SpineRuntimeTransitionRehearsalVerify().verify(executed)

    tampered = copy.deepcopy(card)
    tampered["deployment_id"] = "changed"
    with pytest.raises(
        SpineRuntimeTransitionRehearsalVerifyError,
        match="identity mismatch|digest mismatch",
    ):
        SpineRuntimeTransitionRehearsalVerify().verify(tampered)
