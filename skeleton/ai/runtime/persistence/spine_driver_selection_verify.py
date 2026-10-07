"""Independent verifier for P2 durable driver-selection state."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineDriverSelectionVerifyError(RuntimeError):
    """Driver-selection verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineDriverSelectionVerify:
    """Verify selected-driver state without touching a runtime object."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_driver_selection":
            raise SpineDriverSelectionVerifyError("driver selection kind mismatch")
        if card.get("selection_authorized") is not True:
            raise SpineDriverSelectionVerifyError("selection is not authorized")
        if card.get("permit_consumed") is not True:
            raise SpineDriverSelectionVerifyError("selection permit was not consumed")
        if card.get("runtime_driver_selected") is not True:
            raise SpineDriverSelectionVerifyError("runtime driver was not selected")
        if card.get("target_driver") != "pymongo-async":
            raise SpineDriverSelectionVerifyError("selected target driver changed")
        if card.get("runtime_object_replaced") is not False:
            raise SpineDriverSelectionVerifyError("selection replaced runtime object")
        if card.get("dispatcher_started") is not False:
            raise SpineDriverSelectionVerifyError("selection started dispatcher")
        if card.get("runtime_activated") is not False:
            raise SpineDriverSelectionVerifyError("selection activated runtime")

        for field in ("selection_id", "consumption_digest", "permit_id"):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineDriverSelectionVerifyError(f"{field} is invalid")
        expected_id = hashlib.sha256(
            f"{card['consumption_digest']}|{card['permit_id']}|pymongo-async".encode("utf-8")
        ).hexdigest()
        if card["selection_id"] != expected_id:
            raise SpineDriverSelectionVerifyError("driver selection identity mismatch")

        evidence = {
            "selection_id": card.get("selection_id"),
            "consumption_digest": card.get("consumption_digest"),
            "permit_id": card.get("permit_id"),
            "target_driver": card.get("target_driver"),
            "selected_at": card.get("selected_at"),
            "selection_authorized": card.get("selection_authorized"),
            "permit_consumed": card.get("permit_consumed"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "runtime_object_replaced": card.get("runtime_object_replaced"),
            "dispatcher_started": card.get("dispatcher_started"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineDriverSelectionVerifyError("driver selection digest mismatch")

        return {
            "kind": "spine_driver_selection_verify",
            "hit": False,
            "law": "selection-verification-does-not-activate-runtime",
            "citation": "VOL-134",
            "selection_id": card["selection_id"],
            "selection_digest": digest,
            "verified": True,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
