"""Deployment handoff boundary for the P2 runtime activation path.

The verified final pre-activation boundary may be handed to a deployment
authority, but the handoff itself cannot replace the runtime object, start the
dispatcher, move the fence, or activate runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable


class SpineRuntimeActivationHandoffError(RuntimeError):
    """Deployment handoff evidence is stale, mis-scoped, or unauthenticated."""


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
        raise SpineRuntimeActivationHandoffError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineRuntimeActivationHandoffError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineRuntimeActivationHandoffError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class SpineRuntimeActivationHandoff:
    """Bind pre-activation proof to an authenticated deployment receipt."""

    def qualify(
        self,
        *,
        boundary: dict[str, Any],
        boundary_verify: dict[str, Any],
        receipt: dict[str, Any],
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(boundary, dict)
            or boundary.get("kind") != "spine_runtime_activation_boundary_witness"
            or boundary.get("activation_boundary_verified") is not True
            or boundary.get("runtime_driver_selected") is not True
            or boundary.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationHandoffError("verified pre-activation boundary is required")
        if boundary.get("runtime_object_replaced") is not False:
            raise SpineRuntimeActivationHandoffError("runtime object changed before handoff")
        if boundary.get("dispatcher_running") is not False:
            raise SpineRuntimeActivationHandoffError("dispatcher is running before handoff")
        if boundary.get("dispatcher_called") is not False:
            raise SpineRuntimeActivationHandoffError("dispatcher was called before handoff")
        if boundary.get("fence_moved") is not False:
            raise SpineRuntimeActivationHandoffError("fence moved before handoff")
        boundary_digest = boundary.get("digest")
        commitment_id = boundary.get("commitment_id")
        if not isinstance(boundary_digest, str) or len(boundary_digest) != 64:
            raise SpineRuntimeActivationHandoffError("boundary digest is invalid")
        if not isinstance(commitment_id, str) or len(commitment_id) != 64:
            raise SpineRuntimeActivationHandoffError("commitment identity is invalid")

        if (
            not isinstance(boundary_verify, dict)
            or boundary_verify.get("kind") != "spine_runtime_activation_boundary_verify"
            or boundary_verify.get("verified") is not True
            or boundary_verify.get("boundary_digest") != boundary_digest
            or boundary_verify.get("runtime_driver_selected") is not True
            or boundary_verify.get("dispatcher_running") is not False
            or boundary_verify.get("fence_moved") is not False
            or boundary_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationHandoffError("independent boundary verification is required")

        if not callable(authenticate):
            raise SpineRuntimeActivationHandoffError("deployment authenticator must be callable")
        if not isinstance(receipt, dict) or receipt.get("kind") != "spine_runtime_deployment_receipt":
            raise SpineRuntimeActivationHandoffError("runtime-deployment receipt is missing")
        if receipt.get("authority_domain") != "runtime-deployment":
            raise SpineRuntimeActivationHandoffError("handoff authority must be runtime-deployment")
        if receipt.get("decision") != "accept-handoff":
            raise SpineRuntimeActivationHandoffError("handoff decision must be accept-handoff")
        if receipt.get("boundary_digest") != boundary_digest:
            raise SpineRuntimeActivationHandoffError("handoff boundary scope mismatch")
        if receipt.get("target_driver") != "pymongo-async":
            raise SpineRuntimeActivationHandoffError("handoff target driver changed")

        deployment_id = receipt.get("deployment_id")
        handoff_nonce = receipt.get("handoff_nonce")
        attestation = receipt.get("attestation_digest")
        if not isinstance(deployment_id, str) or not deployment_id or deployment_id != deployment_id.strip():
            raise SpineRuntimeActivationHandoffError("deployment_id must be canonical non-empty text")
        if not isinstance(handoff_nonce, str) or len(handoff_nonce) != 64:
            raise SpineRuntimeActivationHandoffError("handoff nonce is invalid")
        if not isinstance(attestation, str) or len(attestation) != 64:
            raise SpineRuntimeActivationHandoffError("handoff attestation digest is invalid")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeActivationHandoffError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        issued_at = _instant(receipt.get("issued_at"), "issued_at")
        expires_at = _instant(receipt.get("expires_at"), "expires_at")
        if issued_at > instant:
            raise SpineRuntimeActivationHandoffError("handoff receipt is not yet valid")
        if expires_at <= instant or expires_at <= issued_at:
            raise SpineRuntimeActivationHandoffError("handoff receipt is expired or invalid")
        if (expires_at - issued_at).total_seconds() > 300:
            raise SpineRuntimeActivationHandoffError("handoff receipt lifetime exceeds five minutes")

        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineRuntimeActivationHandoffError("deployment authentication failed closed") from exc
        if authenticated is not True:
            raise SpineRuntimeActivationHandoffError("deployment receipt was not externally authenticated")

        evidence = {
            "boundary_digest": boundary_digest,
            "commitment_id": commitment_id,
            "deployment_id": deployment_id,
            "handoff_nonce": handoff_nonce,
            "target_driver": "pymongo-async",
            "handoff_expires_at": expires_at.isoformat(),
            "deployment_receipt_authenticated": True,
            "handoff_ready": True,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "dispatcher_running": False,
            "fence_moved": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_runtime_activation_handoff",
            "hit": False,
            "law": "deployment-handoff-does-not-activate-runtime",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
