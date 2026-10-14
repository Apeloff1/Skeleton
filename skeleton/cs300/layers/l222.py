"""CS300-222 NUMA Placement Engine. No shared trunk. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

LAYER_ID = "CS300-222"
TITLE_KEY = "numa_placement_engine"
KEY = TITLE_KEY
CASES = ("normal", "adversarial", "boundary", "failure", "recovery")
ORDINAL = 222
STATES = ['numa', 'placement', 'engine', 'hold', 'fail', 'restore']


class LayerReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def build(card: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(card, dict) or card.get("layer") != LAYER_ID:
        raise LayerReject("identity mismatch")
    if card.get("stored_prose") not in (0, None):
        raise LayerReject("stored prose")
    if card.get("authority_expansion") is not False:
        raise LayerReject("authority expansion")
    case_matrix = "cases" in card
    if case_matrix:
        cases = card["cases"]
        if not isinstance(cases, dict) or set(cases) != set(CASES):
            raise LayerReject("cases")
        if any(not isinstance(cases[name], dict) for name in CASES):
            raise LayerReject("typed cases")
        normal = cases["normal"].get(KEY)
        recovery = cases["recovery"]
        if cases["adversarial"].get("accepted") is not False:
            raise LayerReject("adversarial")
        if cases["boundary"].get("at_bound") is not True:
            raise LayerReject("boundary")
        if (cases["failure"].get("failed") is not True
                or cases["failure"].get("opened") is not False):
            raise LayerReject("failure opened")
        generation = recovery.get("generation")
        if (recovery.get("restored") is not True
                or type(generation) is not int or generation != ORDINAL):
            raise LayerReject("recovery")
        if ((TITLE_KEY in card and card[TITLE_KEY] != normal)
                or ("generation" in card and card["generation"] != generation)):
            raise LayerReject("conflicting evidence")
        card = dict(card, **{TITLE_KEY: normal, "generation": generation})
    bound = card.get("bound")
    value = card.get(TITLE_KEY)
    if type(bound) is not int or type(value) is not int:
        raise LayerReject("typed contract")
    if value < 0 or value > bound or not 1 <= bound <= 1024:
        raise LayerReject("bound")
    state = STATES[0]
    if card.get("adversary") is True:
        state = "fail"
        raise LayerReject("adversary")
    if card.get("failed") is True and card.get("opened") is True:
        raise LayerReject("failure opened")
    if type(card.get("generation")) is not int or card["generation"] != ORDINAL:
        raise LayerReject("recovery")
    state = "restore"
    if ORDINAL % 10 == 0 and card.get("finality") != LAYER_ID:
        raise LayerReject("finality")
    cost = value + (0 if case_matrix else len(TITLE_KEY)) + ORDINAL
    body = {"layer": LAYER_ID, "state": state, "cost": cost, "states": STATES}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "layer": LAYER_ID,
        "key": TITLE_KEY,
        "state": state,
        "cost": cost,
        "states": list(STATES),
        "digest": digest,
        "built": True,
        "stub": False,
        "cases": list(CASES) if case_matrix else [],
        "trunk": False,
        "stored_prose": 0,
    }
