"""Dry-run deployment transition rehearsal for the P2 runtime spine."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness


class SpineRuntimeTransitionRehearsalError(RuntimeError):
    """Deployment transition rehearsal failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise SpineRuntimeTransitionRehearsalError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineRuntimeTransitionRehearsalError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineRuntimeTransitionRehearsalError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class SpineRuntimeTransitionRehearsal:
    """Recheck deployment handoff against an untouched runtime without executing it."""

    def rehearse(
        self,
        *,
        handoff: dict[str, Any],
        handoff_verify: dict[str, Any],
        runtime: Any,
        epoch_before: int,
        epoch_after: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(handoff, dict)
            or handoff.get("kind") != "spine_runtime_activation_handoff"
            or handoff.get("handoff_ready") is not True
            or handoff.get("deployment_receipt_authenticated") is not True
            or handoff.get("runtime_driver_selected") is not True
            or handoff.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionRehearsalError("verified deployment handoff is required")
        for field in ("runtime_object_replaced", "dispatcher_started", "dispatcher_running", "fence_moved"):
            if handoff.get(field) is not False:
                raise SpineRuntimeTransitionRehearsalError(f"handoff invariant changed: {field}")
        if handoff.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionRehearsalError("handoff target driver changed")

        handoff_digest = handoff.get("digest")
        boundary_digest = handoff.get("boundary_digest")
        handoff_nonce = handoff.get("handoff_nonce")
        if not isinstance(handoff_digest, str) or len(handoff_digest) != 64:
            raise SpineRuntimeTransitionRehearsalError("handoff digest is invalid")
        if not isinstance(boundary_digest, str) or len(boundary_digest) != 64:
            raise SpineRuntimeTransitionRehearsalError("boundary digest is invalid")
        if not isinstance(handoff_nonce, str) or len(handoff_nonce) != 64:
            raise SpineRuntimeTransitionRehearsalError("handoff nonce is invalid")

        if (
            not isinstance(handoff_verify, dict)
            or handoff_verify.get("kind") != "spine_runtime_activation_handoff_verify"
            or handoff_verify.get("verified") is not True
            or handoff_verify.get("handoff_digest") != handoff_digest
            or handoff_verify.get("boundary_digest") != boundary_digest
            or handoff_verify.get("handoff_ready") is not True
            or handoff_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionRehearsalError("independent handoff verification is required")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionRehearsalError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        expires_at = _instant(handoff.get("handoff_expires_at"), "handoff_expires_at")
        if instant >= expires_at:
            raise SpineRuntimeTransitionRehearsalError("deployment handoff expired before rehearsal")

        guard = SpineDispatchGuard()
        before = guard.snapshot(runtime)
        dispatch = guard.compare(before, runtime)
        if dispatch.get("same") is not True or dispatch.get("called") is not False:
            raise SpineRuntimeTransitionRehearsalError("dispatcher identity changed during rehearsal")
        if getattr(runtime, "dispatcher_running", False) is not False:
            raise SpineRuntimeTransitionRehearsalError("runtime dispatcher is running during rehearsal")

        epoch = SpineEpochWitness().card(
            epoch_before=epoch_before,
            epoch_after=epoch_after,
            side=handoff,
        )
        if epoch.get("moved") is not False:
            raise SpineRuntimeTransitionRehearsalError("deployment rehearsal moved fence")

        deployment_id = handoff.get("deployment_id")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionRehearsalError("deployment identity is missing")
        transition_id = hashlib.sha256(
            f"{handoff_digest}|{deployment_id}|{handoff_nonce}|pymongo-async".encode("utf-8")
        ).hexdigest()
        evidence = {
            "transition_id": transition_id,
            "handoff_digest": handoff_digest,
            "boundary_digest": boundary_digest,
            "deployment_id": deployment_id,
            "handoff_nonce": handoff_nonce,
            "target_driver": "pymongo-async",
            "epoch_before": epoch_before,
            "epoch_after": epoch_after,
            "dispatcher_identity_stable": True,
            "dispatcher_called": False,
            "dispatcher_running": False,
            "fence_moved": False,
            "transition_rehearsed": True,
            "transition_attempted": False,
            "transition_executed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_runtime_transition_rehearsal",
            "hit": False,
            "law": "deployment-transition-rehearsal-does-not-execute-activation",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
