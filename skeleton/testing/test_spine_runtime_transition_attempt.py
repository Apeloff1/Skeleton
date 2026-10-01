from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from skeleton.persistence.spine_runtime_transition_attempt import (
    SpineRuntimeTransitionAttemptError,
    SpineRuntimeTransitionAttemptLedger,
)
from skeleton.persistence.spine_runtime_transition_attempt_verify import (
    SpineRuntimeTransitionAttemptVerify,
    SpineRuntimeTransitionAttemptVerifyError,
)


NOW = datetime(2026, 10, 1, 17, 5, tzinfo=timezone.utc)


class Runtime:
    dispatcher_running = False

    def start_dispatcher(self) -> None:
        self.dispatcher_running = True


def _consumption() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_consumption",
        "digest": "c" * 64,
        "permit_id": "p" * 64,
        "rehearsal_digest": "r" * 64,
        "transition_id": "t" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "consumed_at": NOW.isoformat(),
        "transition_authorized": True,
        "permit_consumed": True,
        "transition_attempted": False,
        "transition_executed": False,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "runtime_activated": False,
    }


def _verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_consumption_verify",
        "consumption_digest": "c" * 64,
        "permit_id": "p" * 64,
        "transition_id": "t" * 64,
        "verified": True,
        "transition_authorized": True,
        "permit_consumed": True,
        "transition_attempted": False,
        "transition_executed": False,
        "runtime_driver_selected": True,
        "runtime_activated": False,
    }


def _result(command: dict[str, object]) -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_attempt_result",
        "decision": "refuse-transition",
        "transition_id": command["transition_id"],
        "deployment_id": command["deployment_id"],
        "target_driver": command["target_driver"],
        "attempt_nonce": "n" * 64,
        "reason": "dispatcher-cutover-not-yet-qualified",
        "transition_executed": False,
        "runtime_activated": False,
    }


def test_deployment_owned_transition_attempt_is_recorded_once_and_refused() -> None:
    runtime = Runtime()
    ledger = SpineRuntimeTransitionAttemptLedger()
    try:
        card = ledger.attempt(
            consumption=_consumption(),
            consumption_verify=_verify(),
            runtime=runtime,
            epoch_before=9,
            epoch_after=9,
            execute_attempt=_result,
            now=NOW,
        )
        verified = SpineRuntimeTransitionAttemptVerify().verify(card)

        assert ledger.count() == 1
        assert card["transition_attempted"] is True
        assert card["transition_executed"] is False
        assert card["runtime_object_replaced"] is False
        assert card["dispatcher_started"] is False
        assert card["fence_moved"] is False
        assert card["runtime_activated"] is False
        assert runtime.dispatcher_running is False
        assert verified["verified"] is True

        with pytest.raises(SpineRuntimeTransitionAttemptError, match="replay refused"):
            ledger.attempt(
                consumption=_consumption(),
                consumption_verify=_verify(),
                runtime=runtime,
                epoch_before=9,
                epoch_after=9,
                execute_attempt=_result,
                now=NOW,
            )
    finally:
        ledger.close()


def test_transition_attempt_rejects_execution_or_dispatcher_mutation() -> None:
    runtime = Runtime()
    ledger = SpineRuntimeTransitionAttemptLedger()
    try:
        def executed(command: dict[str, object]) -> dict[str, object]:
            result = _result(command)
            result["transition_executed"] = True
            return result

        with pytest.raises(SpineRuntimeTransitionAttemptError, match="reported execution"):
            ledger.attempt(
                consumption=_consumption(),
                consumption_verify=_verify(),
                runtime=runtime,
                epoch_before=1,
                epoch_after=1,
                execute_attempt=executed,
                now=NOW,
            )

        def starts_dispatcher(command: dict[str, object]) -> dict[str, object]:
            runtime.start_dispatcher()
            return _result(command)

        with pytest.raises(SpineRuntimeTransitionAttemptError, match="dispatcher started"):
            ledger.attempt(
                consumption=_consumption(),
                consumption_verify=_verify(),
                runtime=runtime,
                epoch_before=1,
                epoch_after=1,
                execute_attempt=starts_dispatcher,
                now=NOW,
            )
    finally:
        ledger.close()


def test_transition_attempt_verifier_rejects_tamper() -> None:
    runtime = Runtime()
    ledger = SpineRuntimeTransitionAttemptLedger()
    try:
        card = ledger.attempt(
            consumption=_consumption(),
            consumption_verify=_verify(),
            runtime=runtime,
            epoch_before=2,
            epoch_after=2,
            execute_attempt=_result,
            now=NOW,
        )
        tampered = copy.deepcopy(card)
        tampered["runtime_activated"] = True
        with pytest.raises(SpineRuntimeTransitionAttemptVerifyError, match="runtime_activated"):
            SpineRuntimeTransitionAttemptVerify().verify(tampered)
    finally:
        ledger.close()
