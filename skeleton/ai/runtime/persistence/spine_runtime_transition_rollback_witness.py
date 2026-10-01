"""Independent rollback witness for a refused P2 runtime transition attempt."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness


class SpineRuntimeTransitionRollbackWitnessError(RuntimeError):
    """Rollback witness failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionRollbackWitness:
    """Prove a refused attempt left no runtime effect requiring rollback."""

    def witness(
        self,
        *,
        attempt: dict[str, Any],
        attempt_verify: dict[str, Any],
        runtime: Any,
        epoch_before: int,
        epoch_after: int,
    ) -> dict[str, Any]:
        if (
            not isinstance(attempt, dict)
            or attempt.get("kind") != "spine_runtime_transition_attempt"
            or attempt.get("transition_attempted") is not True
            or attempt.get("transition_executed") is not False
            or attempt.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionRollbackWitnessError("verified refused transition attempt is required")
        if attempt.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionRollbackWitnessError("runtime driver selection is missing")
        for field in ("runtime_object_replaced", "dispatcher_started", "fence_moved"):
            if attempt.get(field) is not False:
                raise SpineRuntimeTransitionRollbackWitnessError(f"attempt invariant changed: {field}")

        attempt_id = attempt.get("attempt_id")
        attempt_digest = attempt.get("digest")
        transition_id = attempt.get("transition_id")
        for field, value in (
            ("attempt identity", attempt_id),
            ("attempt digest", attempt_digest),
            ("transition identity", transition_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionRollbackWitnessError(f"{field} is invalid")

        if (
            not isinstance(attempt_verify, dict)
            or attempt_verify.get("kind") != "spine_runtime_transition_attempt_verify"
            or attempt_verify.get("verified") is not True
            or attempt_verify.get("attempt_id") != attempt_id
            or attempt_verify.get("attempt_digest") != attempt_digest
            or attempt_verify.get("transition_id") != transition_id
            or attempt_verify.get("transition_attempted") is not True
            or attempt_verify.get("transition_executed") is not False
            or attempt_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionRollbackWitnessError("independent transition-attempt verification is required")

        guard = SpineDispatchGuard()
        before = guard.snapshot(runtime)
        dispatch = guard.compare(before, runtime)
        if dispatch.get("same") is not True or dispatch.get("called") is not False:
            raise SpineRuntimeTransitionRollbackWitnessError("dispatcher identity changed during rollback witness")
        if getattr(runtime, "dispatcher_running", False) is not False:
            raise SpineRuntimeTransitionRollbackWitnessError("dispatcher is running after refused transition attempt")

        epoch = SpineEpochWitness().card(
            epoch_before=epoch_before,
            epoch_after=epoch_after,
            side=attempt,
        )
        if epoch.get("moved") is not False:
            raise SpineRuntimeTransitionRollbackWitnessError("fence moved after refused transition attempt")

        evidence = {
            "attempt_id": attempt_id,
            "attempt_digest": attempt_digest,
            "transition_id": transition_id,
            "deployment_id": attempt.get("deployment_id"),
            "target_driver": "pymongo-async",
            "rollback_checked": True,
            "rollback_required": False,
            "rollback_executed": False,
            "rollback_verified": True,
            "transition_attempted": True,
            "transition_executed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_identity_stable": True,
            "dispatcher_started": False,
            "fence_moved": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_runtime_transition_rollback_witness",
            "hit": False,
            "law": "refused-transition-must-prove-no-effect-or-rollback-before-promotion",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
