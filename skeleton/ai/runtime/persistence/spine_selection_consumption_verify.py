"""Independent verifier for one-time P2 selection permit consumption."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineSelectionConsumptionVerifyError(RuntimeError):
    """Selection consumption verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineSelectionConsumptionVerify:
    """Verify permit consumption without selecting or activating runtime."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_selection_consumption":
            raise SpineSelectionConsumptionVerifyError("selection consumption kind mismatch")
        if card.get("selection_authorized") is not True:
            raise SpineSelectionConsumptionVerifyError("selection is not authorized")
        if card.get("permit_consumed") is not True:
            raise SpineSelectionConsumptionVerifyError("permit was not consumed")
        if card.get("runtime_driver_selected") is not False:
            raise SpineSelectionConsumptionVerifyError("consumption already selected runtime driver")
        if card.get("runtime_activated") is not False:
            raise SpineSelectionConsumptionVerifyError("consumption already activated runtime")
        if card.get("target_driver") != "pymongo-async":
            raise SpineSelectionConsumptionVerifyError("selection target driver changed")

        for field in ("permit_id", "permit_digest", "effectiveness_digest", "authorization_digest"):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineSelectionConsumptionVerifyError(f"{field} is invalid")
        consumed_at = card.get("consumed_at")
        if not isinstance(consumed_at, str) or not consumed_at:
            raise SpineSelectionConsumptionVerifyError("consumed_at is missing")

        evidence = {
            "permit_id": card.get("permit_id"),
            "permit_digest": card.get("permit_digest"),
            "effectiveness_digest": card.get("effectiveness_digest"),
            "authorization_digest": card.get("authorization_digest"),
            "target_driver": card.get("target_driver"),
            "consumed_at": consumed_at,
            "selection_authorized": card.get("selection_authorized"),
            "permit_consumed": card.get("permit_consumed"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineSelectionConsumptionVerifyError("selection consumption digest mismatch")

        return {
            "kind": "spine_selection_consumption_verify",
            "hit": False,
            "law": "consumption-verification-does-not-select-runtime",
            "citation": "VOL-134",
            "consumption_digest": digest,
            "permit_id": card["permit_id"],
            "verified": True,
            "selection_authorized": True,
            "permit_consumed": True,
            "runtime_driver_selected": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
