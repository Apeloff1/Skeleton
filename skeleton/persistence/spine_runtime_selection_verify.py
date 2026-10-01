"""Independent verifier for P2 runtime-driver selection candidates."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class SpineRuntimeSelectionVerifyError(RuntimeError):
    """Selection candidate verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeSelectionVerify:
    """Verify candidate identity while preserving the non-selection boundary."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_selection_candidate":
            raise SpineRuntimeSelectionVerifyError("selection candidate kind mismatch")

        plan = SpineMotorPlan().card()
        if card.get("plan_digest") != plan["digest"]:
            raise SpineRuntimeSelectionVerifyError("selection plan digest mismatch")
        if card.get("candidate_driver") != "pymongo-async":
            raise SpineRuntimeSelectionVerifyError("selection candidate driver changed")
        if card.get("indexes_applied") != plan["count"]:
            raise SpineRuntimeSelectionVerifyError("selection candidate indexes incomplete")
        expected_names = [row["name"] for row in plan["indexes"]]
        if card.get("index_names") != expected_names:
            raise SpineRuntimeSelectionVerifyError(
                "selection candidate index identities changed"
            )
        if card.get("dispatcher_identity_stable") is not True:
            raise SpineRuntimeSelectionVerifyError("dispatcher identity is not stable")
        if card.get("dispatcher_called") is not False:
            raise SpineRuntimeSelectionVerifyError("dispatcher was called")
        for flag in ("runtime_driver_selected", "selection_authorized", "runtime_activated"):
            if card.get(flag) is not False:
                raise SpineRuntimeSelectionVerifyError("selection candidate gained authority")

        evidence = {
            "qualification_digest": card.get("qualification_digest"),
            "driver_receipt_digest": card.get("driver_receipt_digest"),
            "preflight_digest": card.get("preflight_digest"),
            "bootstrap_digest": card.get("bootstrap_digest"),
            "plan_digest": card.get("plan_digest"),
            "index_names": card.get("index_names"),
            "driver_distribution": card.get("driver_distribution"),
            "driver_version": card.get("driver_version"),
            "driver_class": card.get("driver_class"),
            "candidate_driver": card.get("candidate_driver"),
            "indexes_applied": card.get("indexes_applied"),
            "dispatcher_identity_stable": card.get("dispatcher_identity_stable"),
            "dispatcher_called": card.get("dispatcher_called"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "selection_authorized": card.get("selection_authorized"),
            "runtime_activated": card.get("runtime_activated"),
        }
        for name in (
            "qualification_digest",
            "driver_receipt_digest",
            "preflight_digest",
            "bootstrap_digest",
        ):
            value = evidence[name]
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeSelectionVerifyError(f"invalid candidate digest: {name}")

        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeSelectionVerifyError("selection candidate digest mismatch")

        return {
            "kind": "spine_runtime_selection_verify",
            "hit": False,
            "law": "selection-verification-does-not-authorize",
            "citation": "VOL-134",
            "candidate_digest": digest,
            "verified": True,
            "candidate_driver": "pymongo-async",
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
