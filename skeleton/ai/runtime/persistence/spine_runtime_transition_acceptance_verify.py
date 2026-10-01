"""Independent verifier for P2 post-transition acceptance evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionAcceptanceVerifyError(RuntimeError):
    """Transition acceptance verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionAcceptanceVerify:
    """Verify external acceptance without granting activation authority."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind") != "spine_runtime_transition_acceptance"
        ):
            raise SpineRuntimeTransitionAcceptanceVerifyError(
                "transition acceptance kind mismatch"
            )
        for field in (
            "acceptance_authenticated",
            "health_qualified",
            "operation_continuity",
            "activation_accepted",
            "rollback_available",
        ):
            if card.get(field) is not True:
                raise SpineRuntimeTransitionAcceptanceVerifyError(
                    f"acceptance invariant missing: {field}"
                )
        if card.get("production_activation_authorized") is not False:
            raise SpineRuntimeTransitionAcceptanceVerifyError(
                "acceptance cannot authorize production activation"
            )
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeTransitionAcceptanceVerifyError(
                "acceptance cannot self-activate runtime"
            )
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionAcceptanceVerifyError(
                "acceptance target driver changed"
            )
        for field in (
            "acceptance_id",
            "health_digest",
            "execution_id",
            "acceptance_nonce",
        ):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionAcceptanceVerifyError(
                    f"{field} is invalid"
                )
        for field in ("deployment_id", "accepted_at", "valid_until"):
            value = card.get(field)
            if not isinstance(value, str) or not value:
                raise SpineRuntimeTransitionAcceptanceVerifyError(
                    f"{field} is missing"
                )

        expected_id = hashlib.sha256(
            (
                f"{card['health_digest']}|{card['execution_id']}|"
                f"{card['deployment_id']}|{card['acceptance_nonce']}|"
                "pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        if card["acceptance_id"] != expected_id:
            raise SpineRuntimeTransitionAcceptanceVerifyError(
                "transition acceptance identity mismatch"
            )
        evidence = {
            "acceptance_id": card["acceptance_id"],
            "health_digest": card["health_digest"],
            "execution_id": card["execution_id"],
            "deployment_id": card["deployment_id"],
            "acceptance_nonce": card["acceptance_nonce"],
            "target_driver": card["target_driver"],
            "accepted_at": card["accepted_at"],
            "valid_until": card["valid_until"],
            "acceptance_authenticated": card["acceptance_authenticated"],
            "health_qualified": card["health_qualified"],
            "operation_continuity": card["operation_continuity"],
            "activation_accepted": card["activation_accepted"],
            "production_activation_authorized": card[
                "production_activation_authorized"
            ],
            "rollback_available": card["rollback_available"],
            "runtime_activated": card["runtime_activated"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeTransitionAcceptanceVerifyError(
                "transition acceptance digest mismatch"
            )
        return {
            "kind": "spine_runtime_transition_acceptance_verify",
            "hit": True,
            "law": "acceptance-verification-does-not-promote-runtime-activation",
            "citation": "VOL-134",
            "acceptance_id": card["acceptance_id"],
            "acceptance_digest": digest,
            "health_digest": card["health_digest"],
            "execution_id": card["execution_id"],
            "deployment_id": card["deployment_id"],
            "target_driver": card["target_driver"],
            "valid_until": card["valid_until"],
            "verified": True,
            "activation_accepted": True,
            "production_activation_authorized": False,
            "rollback_available": True,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
