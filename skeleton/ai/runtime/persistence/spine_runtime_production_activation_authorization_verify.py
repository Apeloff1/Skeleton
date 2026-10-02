"""Independent verifier for P2 production activation authorization."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeProductionActivationAuthorizationVerifyError(RuntimeError):
    """Production activation authorization verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeProductionActivationAuthorizationVerify:
    """Verify external activation authority without activating the runtime."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind")
            != "spine_runtime_production_activation_authorization"
        ):
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "production activation authorization kind mismatch"
            )
        if card.get("authorization_authenticated") is not True:
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "production activation authorization is not authenticated"
            )
        if card.get("activation_accepted") is not True:
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "activation acceptance disappeared"
            )
        if card.get("production_activation_authorized") is not True:
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "production activation is not authorized"
            )
        if card.get("rollback_available") is not True:
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "rollback availability disappeared"
            )
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "authorization cannot self-activate runtime"
            )
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "activation target driver changed"
            )
        for field in (
            "authorization_id",
            "acceptance_digest",
            "acceptance_id",
            "health_digest",
            "execution_id",
            "authorization_nonce",
        ):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                    f"{field} is invalid"
                )
        for field in ("deployment_id", "authorized_at", "valid_until"):
            value = card.get(field)
            if not isinstance(value, str) or not value:
                raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                    f"{field} is missing"
                )

        expected_id = hashlib.sha256(
            (
                f"{card['acceptance_digest']}|{card['acceptance_id']}|"
                f"{card['health_digest']}|{card['execution_id']}|"
                f"{card['deployment_id']}|"
                f"{card['authorization_nonce']}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        if card["authorization_id"] != expected_id:
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "production activation authorization identity mismatch"
            )
        evidence = {
            "authorization_id": card["authorization_id"],
            "acceptance_digest": card["acceptance_digest"],
            "acceptance_id": card["acceptance_id"],
            "health_digest": card["health_digest"],
            "execution_id": card["execution_id"],
            "deployment_id": card["deployment_id"],
            "authorization_nonce": card["authorization_nonce"],
            "target_driver": card["target_driver"],
            "authorized_at": card["authorized_at"],
            "valid_until": card["valid_until"],
            "authorization_authenticated": card["authorization_authenticated"],
            "activation_accepted": card["activation_accepted"],
            "production_activation_authorized": card[
                "production_activation_authorized"
            ],
            "rollback_available": card["rollback_available"],
            "runtime_activated": card["runtime_activated"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeProductionActivationAuthorizationVerifyError(
                "production activation authorization digest mismatch"
            )
        return {
            "kind": "spine_runtime_production_activation_authorization_verify",
            "hit": True,
            "law": "authorization-verification-does-not-activate-runtime",
            "citation": "VOL-134",
            "authorization_id": card["authorization_id"],
            "authorization_digest": digest,
            "acceptance_id": card["acceptance_id"],
            "health_digest": card["health_digest"],
            "execution_id": card["execution_id"],
            "deployment_id": card["deployment_id"],
            "target_driver": card["target_driver"],
            "valid_until": card["valid_until"],
            "verified": True,
            "production_activation_authorized": True,
            "rollback_available": True,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
