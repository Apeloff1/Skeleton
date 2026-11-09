"""Independent verifier for P2 cutover authorization effectiveness."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineCutoverEffectivenessVerifyError(RuntimeError):
    """Effectiveness verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineCutoverEffectivenessVerify:
    """Verify effective authorization while preserving non-selection."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_cutover_effectiveness":
            raise SpineCutoverEffectivenessVerifyError("effectiveness kind mismatch")
        if card.get("external_change_control_authenticated") is not True:
            raise SpineCutoverEffectivenessVerifyError("external change control is not authenticated")
        if card.get("authorization_effective") is not True:
            raise SpineCutoverEffectivenessVerifyError("authorization is not effective")
        for flag in ("selection_authorized", "runtime_driver_selected", "runtime_activated"):
            if card.get(flag) is not False:
                raise SpineCutoverEffectivenessVerifyError("effectiveness evidence gained runtime authority")

        authorization_digest = card.get("authorization_digest")
        if not isinstance(authorization_digest, str) or len(authorization_digest) != 64:
            raise SpineCutoverEffectivenessVerifyError("authorization digest is invalid")
        receipt = card.get("effectiveness_receipt")
        if not isinstance(receipt, dict):
            raise SpineCutoverEffectivenessVerifyError("effectiveness receipt is missing")
        if receipt.get("authorization_digest") != authorization_digest:
            raise SpineCutoverEffectivenessVerifyError("effectiveness receipt scope mismatch")
        if receipt.get("authority_domain") != "change-control":
            raise SpineCutoverEffectivenessVerifyError("effectiveness authority changed")
        if receipt.get("decision") != "make-effective":
            raise SpineCutoverEffectivenessVerifyError("effectiveness decision changed")
        if receipt.get("externally_authenticated") is not True:
            raise SpineCutoverEffectivenessVerifyError("effectiveness authentication evidence missing")
        for field in ("one_time_nonce", "attestation_digest"):
            value = receipt.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineCutoverEffectivenessVerifyError(f"invalid effectiveness field: {field}")

        evidence = {
            "authorization_digest": authorization_digest,
            "effectiveness_receipt": dict(receipt),
            "external_change_control_authenticated": card.get("external_change_control_authenticated"),
            "authorization_effective": card.get("authorization_effective"),
            "selection_authorized": card.get("selection_authorized"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineCutoverEffectivenessVerifyError("effectiveness digest mismatch")

        return {
            "kind": "spine_cutover_effectiveness_verify",
            "hit": False,
            "law": "effectiveness-verification-does-not-select-runtime",
            "citation": "VOL-134",
            "effectiveness_digest": digest,
            "authorization_digest": authorization_digest,
            "one_time_nonce": receipt["one_time_nonce"],
            "verified": True,
            "authorization_effective": True,
            "selection_authorized": False,
            "runtime_driver_selected": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
