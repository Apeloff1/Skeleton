"""External effectiveness gate for qualified P2 cutover authorization.

Qualified dual-control evidence is not self-effective. This seam requires a
separate deployment-owned change-control receipt authenticated through an
injected verifier. Effectiveness may become true, but driver selection and
runtime activation remain false.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable


class SpineCutoverEffectivenessError(RuntimeError):
    """Effectiveness evidence is invalid, stale, mis-scoped, or unauthenticated."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SpineCutoverEffectivenessError(f"{field} must be canonical non-empty text")
    return value


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise SpineCutoverEffectivenessError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineCutoverEffectivenessError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineCutoverEffectivenessError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class SpineCutoverEffectiveness:
    """Make qualified authorization effective only with external change control."""

    def qualify(
        self,
        *,
        authorization: dict[str, Any],
        authorization_verify: dict[str, Any],
        receipt: dict[str, Any],
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(authorization, dict)
            or authorization.get("kind") != "spine_cutover_authorization"
            or authorization.get("dual_control_authenticated") is not True
            or authorization.get("authorization_qualified") is not True
        ):
            raise SpineCutoverEffectivenessError("qualified dual-control authorization is required")
        if authorization.get("authorization_effective") is not False:
            raise SpineCutoverEffectivenessError("authorization is already effective")
        for flag in ("selection_authorized", "runtime_driver_selected", "runtime_activated"):
            if authorization.get(flag) is not False:
                raise SpineCutoverEffectivenessError("authorization already gained runtime authority")
        authorization_digest = authorization.get("digest")
        if not isinstance(authorization_digest, str) or len(authorization_digest) != 64:
            raise SpineCutoverEffectivenessError("authorization digest is invalid")

        if (
            not isinstance(authorization_verify, dict)
            or authorization_verify.get("kind") != "spine_cutover_authorization_verify"
            or authorization_verify.get("verified") is not True
            or authorization_verify.get("authorization_digest") != authorization_digest
        ):
            raise SpineCutoverEffectivenessError("independent authorization verification is required")
        if authorization_verify.get("authorization_effective") is not False:
            raise SpineCutoverEffectivenessError("verification card already made authorization effective")
        for flag in ("selection_authorized", "runtime_driver_selected", "runtime_activated"):
            if authorization_verify.get(flag) is not False:
                raise SpineCutoverEffectivenessError(
                    "authorization verification already gained runtime authority"
                )

        if not callable(authenticate):
            raise SpineCutoverEffectivenessError("effectiveness authenticator must be callable")
        if not isinstance(receipt, dict) or receipt.get("kind") != "spine_cutover_effectiveness_receipt":
            raise SpineCutoverEffectivenessError("effectiveness receipt is missing")
        if receipt.get("decision") != "make-effective":
            raise SpineCutoverEffectivenessError("effectiveness decision must be make-effective")
        if receipt.get("authority_domain") != "change-control":
            raise SpineCutoverEffectivenessError("effectiveness authority must be change-control")
        if receipt.get("authorization_digest") != authorization_digest:
            raise SpineCutoverEffectivenessError("effectiveness authorization scope mismatch")

        receipt_id = _text(receipt.get("receipt_id"), "receipt_id")
        window_id = _text(receipt.get("change_window_id"), "change_window_id")
        nonce = receipt.get("one_time_nonce")
        if not isinstance(nonce, str) or len(nonce) != 64:
            raise SpineCutoverEffectivenessError("one_time_nonce must be 64-character text")
        attestation = receipt.get("attestation_digest")
        if not isinstance(attestation, str) or len(attestation) != 64:
            raise SpineCutoverEffectivenessError("effectiveness attestation digest is invalid")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineCutoverEffectivenessError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        issued_at = _instant(receipt.get("issued_at"), "issued_at")
        expires_at = _instant(receipt.get("expires_at"), "expires_at")
        if issued_at > instant:
            raise SpineCutoverEffectivenessError("effectiveness receipt is not yet valid")
        if expires_at <= instant or expires_at <= issued_at:
            raise SpineCutoverEffectivenessError("effectiveness receipt is expired or invalid")
        if (expires_at - issued_at).total_seconds() > 600:
            raise SpineCutoverEffectivenessError("effectiveness receipt lifetime exceeds 10 minutes")

        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineCutoverEffectivenessError("effectiveness authentication failed closed") from exc
        if authenticated is not True:
            raise SpineCutoverEffectivenessError("effectiveness receipt was not externally authenticated")

        normalized = {
            "kind": "spine_cutover_effectiveness_receipt",
            "receipt_id": receipt_id,
            "authorization_digest": authorization_digest,
            "decision": "make-effective",
            "authority_domain": "change-control",
            "change_window_id": window_id,
            "one_time_nonce": nonce,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "attestation_digest": attestation,
            "externally_authenticated": True,
        }
        evidence = {
            "authorization_digest": authorization_digest,
            "effectiveness_receipt": normalized,
            "external_change_control_authenticated": True,
            "authorization_effective": True,
            "selection_authorized": False,
            "runtime_driver_selected": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_cutover_effectiveness",
            "hit": False,
            "law": "external-change-control-makes-authorization-effective-not-runtime-active",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
