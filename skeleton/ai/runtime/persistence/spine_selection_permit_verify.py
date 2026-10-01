"""Independent verifier for durable P2 selection permit cards."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineSelectionPermitVerifyError(RuntimeError):
    """Selection permit verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineSelectionPermitVerify:
    """Verify that authorization permits selection without performing it."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_selection_permit":
            raise SpineSelectionPermitVerifyError("selection permit kind mismatch")
        if card.get("selection_authorized") is not True:
            raise SpineSelectionPermitVerifyError("selection permit is not authorized")
        if card.get("permit_consumed") is not False:
            raise SpineSelectionPermitVerifyError("selection permit was already consumed")
        if card.get("runtime_driver_selected") is not False:
            raise SpineSelectionPermitVerifyError("permit already selected a runtime driver")
        if card.get("runtime_activated") is not False:
            raise SpineSelectionPermitVerifyError("permit already activated runtime")
        if card.get("target_driver") != "pymongo-async":
            raise SpineSelectionPermitVerifyError("selection target driver changed")

        permit_id = card.get("permit_id")
        effectiveness_digest = card.get("effectiveness_digest")
        authorization_digest = card.get("authorization_digest")
        nonce = card.get("one_time_nonce")
        for field, value in (
            ("permit_id", permit_id),
            ("effectiveness_digest", effectiveness_digest),
            ("authorization_digest", authorization_digest),
            ("one_time_nonce", nonce),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineSelectionPermitVerifyError(f"{field} is invalid")

        expected_permit_id = hashlib.sha256(
            f"{effectiveness_digest}|{nonce}|pymongo-async".encode("utf-8")
        ).hexdigest()
        if permit_id != expected_permit_id:
            raise SpineSelectionPermitVerifyError("selection permit identity mismatch")

        permit_valid_until = card.get("permit_valid_until")
        if not isinstance(permit_valid_until, str) or not permit_valid_until:
            raise SpineSelectionPermitVerifyError("permit validity boundary is missing")

        evidence = {
            "effectiveness_digest": effectiveness_digest,
            "authorization_digest": authorization_digest,
            "one_time_nonce": nonce,
            "target_driver": card.get("target_driver"),
            "issued_at": card.get("issued_at"),
            "permit_valid_until": permit_valid_until,
            "selection_authorized": card.get("selection_authorized"),
            "permit_consumed": card.get("permit_consumed"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineSelectionPermitVerifyError("selection permit digest mismatch")

        return {
            "kind": "spine_selection_permit_verify",
            "hit": False,
            "law": "permit-verification-does-not-select-runtime",
            "citation": "VOL-134",
            "permit_id": permit_id,
            "permit_digest": digest,
            "verified": True,
            "selection_authorized": True,
            "permit_consumed": False,
            "runtime_driver_selected": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
