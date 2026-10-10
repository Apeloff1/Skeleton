"""CS300-289 Cross-Layer Optimization Arbiter. No shared trunk. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

LAYER_ID = "CS300-289"
TITLE_KEY = "cross_layer_optimization_arbiter"
ORDINAL = 289
STATES = ['cross', 'layer', 'optimization', 'arbiter', 'hold', 'fail', 'restore']


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
    bound = card.get("bound")
    value = card.get(TITLE_KEY)
    if not isinstance(bound, int) or not isinstance(value, int):
        raise LayerReject("typed contract")
    if value < 0 or value > bound or bound > 1024:
        raise LayerReject("bound")
    state = STATES[0]
    if card.get("adversary") is True:
        state = "fail"
        raise LayerReject("adversary")
    if card.get("failed") is True and card.get("opened") is True:
        raise LayerReject("failure opened")
    if card.get("generation") != ORDINAL:
        raise LayerReject("recovery")
    state = "restore"
    if ORDINAL % 10 == 0 and card.get("finality") != LAYER_ID:
        raise LayerReject("finality")
    cost = value + len(TITLE_KEY) + ORDINAL
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
        "trunk": False,
        "stored_prose": 0,
    }
