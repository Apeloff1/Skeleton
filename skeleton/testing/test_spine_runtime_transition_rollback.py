from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_runtime_transition_rollback_witness import (
    SpineRuntimeTransitionRollbackWitness,
    SpineRuntimeTransitionRollbackWitnessError,
)
from skeleton.persistence.spine_runtime_transition_rollback_verify import (
    SpineRuntimeTransitionRollbackVerify,
    SpineRuntimeTransitionRollbackVerifyError,
)


class Runtime:
    dispatcher_running = False

    def start_dispatcher(self) -> None:
        self.dispatcher_running = True


def _attempt() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_attempt",
        "attempt_id": "a" * 64,
        "digest": "d" * 64,
        "consumption_digest": "c" * 64,
        "permit_id": "p" * 64,
        "transition_id": "t" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "attempt_nonce": "n" * 64,
        "attempted_at": "2026-10-01T17:05:00+00:00",
        "result_digest": "r" * 64,
        "refusal_reason": "dispatcher-cutover-not-yet-qualified",
        "transition_authorized": True,
        "permit_consumed": True,
        "transition_attempted": True,
        "transition_executed": False,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_identity_stable": True,
        "dispatcher_started": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def _verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_attempt_verify",
        "attempt_id": "a" * 64,
        "attempt_digest": "d" * 64,
        "transition_id": "t" * 64,
        "verified": True,
        "transition_attempted": True,
        "transition_executed": False,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def test_refused_attempt_gets_independent_no_effect_rollback_witness() -> None:
    runtime = Runtime()
    card = SpineRuntimeTransitionRollbackWitness().witness(
        attempt=_attempt(),
        attempt_verify=_verify(),
        runtime=runtime,
        epoch_before=12,
        epoch_after=12,
    )
    verified = SpineRuntimeTransitionRollbackVerify().verify(card)

    assert card["rollback_checked"] is True
    assert card["rollback_required"] is False
    assert card["rollback_executed"] is False
    assert card["rollback_verified"] is True
    assert card["transition_executed"] is False
    assert card["runtime_object_replaced"] is False
    assert card["dispatcher_started"] is False
    assert card["fence_moved"] is False
    assert card["runtime_activated"] is False
    assert verified["verified"] is True


def test_rollback_witness_rejects_moved_fence_or_running_dispatcher() -> None:
    with pytest.raises(SpineRuntimeTransitionRollbackWitnessError, match="side card moved the fence"):
        SpineRuntimeTransitionRollbackWitness().witness(
            attempt=_attempt(),
            attempt_verify=_verify(),
            runtime=Runtime(),
            epoch_before=4,
            epoch_after=5,
        )

    runtime = Runtime()
    runtime.dispatcher_running = True
    with pytest.raises(SpineRuntimeTransitionRollbackWitnessError, match="dispatcher is running"):
        SpineRuntimeTransitionRollbackWitness().witness(
            attempt=_attempt(),
            attempt_verify=_verify(),
            runtime=runtime,
            epoch_before=4,
            epoch_after=4,
        )


def test_rollback_verifier_rejects_tamper() -> None:
    card = SpineRuntimeTransitionRollbackWitness().witness(
        attempt=_attempt(),
        attempt_verify=_verify(),
        runtime=Runtime(),
        epoch_before=8,
        epoch_after=8,
    )
    tampered = copy.deepcopy(card)
    tampered["rollback_required"] = True
    with pytest.raises(SpineRuntimeTransitionRollbackVerifyError, match="unexpectedly executed rollback"):
        SpineRuntimeTransitionRollbackVerify().verify(tampered)
