"""Independent verifier for P2 cutover rehearsal evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineCutoverRehearsalVerifyError(RuntimeError):
    """Cutover rehearsal verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineCutoverRehearsalVerify:
    """Verify rehearsal evidence without granting cutover authority."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_cutover_rehearsal":
            raise SpineCutoverRehearsalVerifyError("rehearsal kind mismatch")
        if card.get("rehearsed") is not True:
            raise SpineCutoverRehearsalVerifyError("rehearsal did not complete")
        if card.get("preconditions_green") is not True:
            raise SpineCutoverRehearsalVerifyError("rehearsal preconditions are not green")
        if card.get("chain_match") is not True:
            raise SpineCutoverRehearsalVerifyError("rehearsal chain mismatch")
        if card.get("switch_refused") is not True:
            raise SpineCutoverRehearsalVerifyError("cut gate did not refuse switch")
        if card.get("switch_reason") != "switch-not-landed":
            raise SpineCutoverRehearsalVerifyError("cut gate refusal reason changed")
        if card.get("applied_fence") is not False:
            raise SpineCutoverRehearsalVerifyError("rehearsal advanced a fence")
        for flag in ("runtime_driver_selected", "selection_authorized", "runtime_activated"):
            if card.get(flag) is not False:
                raise SpineCutoverRehearsalVerifyError("rehearsal gained runtime authority")

        candidate_digest = card.get("candidate_digest")
        if not isinstance(candidate_digest, str) or len(candidate_digest) != 64:
            raise SpineCutoverRehearsalVerifyError("candidate digest is invalid")

        evidence = {
            "candidate_digest": candidate_digest,
            "cutover_pending": card.get("cutover_pending"),
            "cutover_published": card.get("cutover_published"),
            "sqlite_epoch": card.get("sqlite_epoch"),
            "mongo_epoch": card.get("mongo_epoch"),
            "chain_match": card.get("chain_match"),
            "preconditions_green": card.get("preconditions_green"),
            "switch_refused": card.get("switch_refused"),
            "switch_reason": card.get("switch_reason"),
            "applied_fence": card.get("applied_fence"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "selection_authorized": card.get("selection_authorized"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineCutoverRehearsalVerifyError("rehearsal digest mismatch")

        return {
            "kind": "spine_cutover_rehearsal_verify",
            "hit": False,
            "law": "rehearsal-verification-does-not-authorize-cutover",
            "citation": "VOL-134",
            "rehearsal_digest": digest,
            "verified": True,
            "switch_refused": True,
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
