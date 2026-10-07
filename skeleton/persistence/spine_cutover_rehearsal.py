"""Fail-closed cutover rehearsal for the P2 runtime spine.

The rehearsal requires every pre-cut prerequisite to be green, then proves the
existing cut gate still refuses the switch because no authorization has landed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_cut_gate import SpineCutGate


class SpineCutoverRehearsalError(RuntimeError):
    """Cutover rehearsal evidence was incomplete or gained authority."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineCutoverRehearsal:
    """Exercise the cut gate with green reads without permitting a switch."""

    def rehearse(
        self,
        *,
        candidate: dict[str, Any],
        selection_verify: dict[str, Any],
        cutover: dict[str, Any],
        chain: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            not isinstance(candidate, dict)
            or candidate.get("kind") != "spine_runtime_selection_candidate"
        ):
            raise SpineCutoverRehearsalError("runtime selection candidate is missing")
        if candidate.get("runtime_driver_selected") is not False:
            raise SpineCutoverRehearsalError("runtime driver was already selected")
        if candidate.get("selection_authorized") is not False:
            raise SpineCutoverRehearsalError("selection was already authorized")
        if candidate.get("runtime_activated") is not False:
            raise SpineCutoverRehearsalError("runtime was already activated")
        candidate_digest = candidate.get("digest")
        if not isinstance(candidate_digest, str) or len(candidate_digest) != 64:
            raise SpineCutoverRehearsalError("candidate digest is invalid")

        if (
            not isinstance(selection_verify, dict)
            or selection_verify.get("kind") != "spine_runtime_selection_verify"
            or selection_verify.get("verified") is not True
            or selection_verify.get("candidate_digest") != candidate_digest
        ):
            raise SpineCutoverRehearsalError("selection verification is missing or mismatched")
        if selection_verify.get("selection_authorized") is not False:
            raise SpineCutoverRehearsalError("selection verification gained authority")
        if selection_verify.get("runtime_activated") is not False:
            raise SpineCutoverRehearsalError("selection verification activated runtime")

        if not isinstance(cutover, dict) or cutover.get("kind") != "spine_cutover":
            raise SpineCutoverRehearsalError("cutover read is missing")
        if cutover.get("hit") is not True:
            raise SpineCutoverRehearsalError("cutover prerequisite reads are not green")
        if cutover.get("applied") != 0:
            raise SpineCutoverRehearsalError("apply gate is not closed")
        if cutover.get("apply_refused") is not True:
            raise SpineCutoverRehearsalError("apply refusal proof is missing")

        if not isinstance(chain, dict) or chain.get("match") is not True:
            raise SpineCutoverRehearsalError("chain prerequisite is not green")

        gate = SpineCutGate().consider(cutover, chain)
        if gate.get("switched") is not False:
            raise SpineCutoverRehearsalError("cut gate switched during rehearsal")
        if gate.get("applied_fence") is not False:
            raise SpineCutoverRehearsalError("cut gate advanced a fence during rehearsal")
        if gate.get("reasons") != ["switch-not-landed"]:
            raise SpineCutoverRehearsalError("cut gate refusal reason changed")

        evidence = {
            "candidate_digest": candidate_digest,
            "cutover_pending": cutover.get("pending"),
            "cutover_published": cutover.get("published"),
            "sqlite_epoch": cutover.get("sqlite_epoch"),
            "mongo_epoch": cutover.get("mongo_epoch"),
            "chain_match": True,
            "preconditions_green": True,
            "switch_refused": True,
            "switch_reason": "switch-not-landed",
            "applied_fence": False,
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_cutover_rehearsal",
            "hit": False,
            "law": "green-preconditions-do-not-authorize-cutover",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "rehearsed": True,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
