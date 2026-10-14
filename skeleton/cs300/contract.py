"""Ladder acceptance runner. Five cases, no authority expansion. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

CASES = ("normal", "adversarial", "boundary", "failure", "recovery")


class ContractReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def run(layer_id: str, key: str, ordinal: int, card: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(card, dict) or card.get("layer") != layer_id:
        raise ContractReject("identity mismatch")
    if card.get("stored_prose") not in (0, None):
        raise ContractReject("stored prose")
    if card.get("authority_expansion") is not False:
        raise ContractReject("authority expansion")
    if not isinstance(card.get("bound"), int) or not 1 <= card["bound"] <= 1024:
        raise ContractReject("bound")
    cases = card.get("cases")
    if not isinstance(cases, dict) or set(cases) != set(CASES):
        raise ContractReject("cases")
    if cases["normal"].get(key) in (None, "", [], {}):
        raise ContractReject("normal")
    if cases["adversarial"].get("accepted") is not False:
        raise ContractReject("adversarial")
    if cases["boundary"].get("at_bound") is not True:
        raise ContractReject("boundary")
    if cases["failure"].get("failed") is not True or cases["failure"].get("opened") is not False:
        raise ContractReject("failure")
    if cases["recovery"].get("restored") is not True:
        raise ContractReject("recovery")
    if ordinal % 10 == 0 and card.get("finality") != layer_id:
        raise ContractReject("finality")
    body = {"layer": layer_id, "key": key, "ordinal": ordinal, "cases": list(CASES)}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "layer": layer_id,
        "key": key,
        "ordinal": ordinal,
        "digest": digest,
        "cases": list(CASES),
        "built": True,
        "stored_prose": 0,
    }
