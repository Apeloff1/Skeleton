"""Fail-closed P4 production envelopes. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

TASKS = (
    "P4-FARM-01",
    "P4-RIGHTS-01",
    "P4-LIFECYCLE-01",
    "P4-SANDBOX-01",
    "P4-LOCALITY-01",
    "P4-CACHE-01",
)


class P4Reject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def admit(task_id: str, card: dict[str, Any]) -> dict[str, Any]:
    if task_id not in TASKS:
        raise P4Reject("unknown task")
    if not isinstance(card, dict) or card.get("task") != task_id:
        raise P4Reject("identity mismatch")
    if card.get("stored_prose") not in (0, None):
        raise P4Reject("stored prose")
    if not isinstance(card.get("bound"), int) or not 1 <= card["bound"] <= 512:
        raise P4Reject("bound")
    if card.get("evidence") in (None, "", [], {}):
        raise P4Reject("missing evidence")
    _gate(task_id, card)
    body = {"task": task_id, "bound": card["bound"], "evidence": card["evidence"]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"task": task_id, "digest": digest, "admitted": True, "stored_prose": 0}


def _gate(task_id: str, card: dict[str, Any]) -> None:
    if task_id == "P4-FARM-01":
        if not isinstance(card.get("quota"), int) or card["quota"] > card["bound"]:
            raise P4Reject("farm quota")
        if card.get("queue") not in ("build", "eval", "research"):
            raise P4Reject("farm queue")
    elif task_id == "P4-RIGHTS-01":
        if card.get("allowed") is not True:
            raise P4Reject("rights denied")
        if card.get("license") in (None, ""):
            raise P4Reject("license")
    elif task_id == "P4-LIFECYCLE-01":
        if card.get("deprecated") is True and card.get("stage") == "serve":
            raise P4Reject("deprecated serve")
        if card.get("stage") not in ("hold", "serve", "retire"):
            raise P4Reject("stage")
    elif task_id == "P4-SANDBOX-01":
        if card.get("isolated") is not True:
            raise P4Reject("sandbox escape")
        if card.get("flag") != "off":
            raise P4Reject("flag default")
    elif task_id == "P4-LOCALITY-01":
        if card.get("tier") not in ("hot", "warm", "cold"):
            raise P4Reject("tier")
        if not isinstance(card.get("bytes"), int) or card["bytes"] < 0 or card["bytes"] > card["bound"]:
            raise P4Reject("locality bytes")
    elif task_id == "P4-CACHE-01":
        if card.get("bound_cache") is not True:
            raise P4Reject("cache unbound")
        if card.get("speculative") is True and card.get("verified") is not True:
            raise P4Reject("unverified speculation")
