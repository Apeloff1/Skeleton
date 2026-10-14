"""Fail-closed envelopes for the six P3 foundation tasks.

Each task has its own adversary. A shared stamp is rejected.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

TASKS = (
    "P3-MODEL-FOUNDATION-01",
    "P3-DOMAIN-INTELLIGENCE-01",
    "P3-TRUST-EXPERIENCE-01",
    "P3-VERTICAL-SUITE-01",
    "P3-ACCEPTANCE-01",
    "P3-CONSTRUCTION-AUTHORITY-01",
)
SLICES = ("VS-002", "VS-003", "VS-004", "VS-005", "VS-006", "VS-007")


class P3Reject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def admit(task_id: str, card: dict[str, Any]) -> dict[str, Any]:
    if task_id not in TASKS:
        raise P3Reject("unknown task")
    if not isinstance(card, dict) or card.get("task") != task_id:
        raise P3Reject("identity mismatch")
    if card.get("stored_prose") not in (0, None):
        raise P3Reject("stored prose")
    _gate(task_id, card)
    body = {"task": task_id, "bound": card.get("bound"), "evidence": card.get("evidence")}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"task": task_id, "digest": digest, "admitted": True, "stored_prose": 0}


def _gate(task_id: str, card: dict[str, Any]) -> None:
    if not isinstance(card.get("bound"), int) or not 1 <= card["bound"] <= 256:
        raise P3Reject("bound")
    if card.get("evidence") in (None, "", [], {}):
        raise P3Reject("missing evidence")
    if task_id == "P3-MODEL-FOUNDATION-01":
        if card.get("provenance") in (None, ""):
            raise P3Reject("provenance")
        if card.get("provider_regression") is not False:
            raise P3Reject("provider regression")
    elif task_id == "P3-DOMAIN-INTELLIGENCE-01":
        if not isinstance(card.get("specialization"), int) or card["specialization"] > card["bound"]:
            raise P3Reject("unbounded specialization")
        if card.get("custody") != "jeeves":
            raise P3Reject("custody")
    elif task_id == "P3-TRUST-EXPERIENCE-01":
        if card.get("operation_id") in (None, ""):
            raise P3Reject("explanation unbound")
        if card.get("presentation_only") is not False:
            raise P3Reject("presentation-only claim")
    elif task_id == "P3-VERTICAL-SUITE-01":
        slices = card.get("slices")
        if not isinstance(slices, list) or set(slices) != set(SLICES):
            raise P3Reject("slice set")
        if card.get("independent") is not True:
            raise P3Reject("evidence not independent")
    elif task_id == "P3-ACCEPTANCE-01":
        needed = {"negative", "aging", "recovery", "independent"}
        have = set(card.get("envelopes") or [])
        if not needed <= have:
            raise P3Reject("acceptance envelope")
    elif task_id == "P3-CONSTRUCTION-AUTHORITY-01":
        if card.get("projection") is not True:
            raise P3Reject("not a projection")
        if card.get("self_promoting") is not False:
            raise P3Reject("self-promotion")
