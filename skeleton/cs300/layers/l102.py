"""CS300-102 runner. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

LAYER_ID = "CS300-102"
KEY = "serializable_isolation_engine"
ORDINAL = 102
FINALITY = False


class LayerReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def admit(card: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(card, dict) or card.get("layer") != LAYER_ID:
        raise LayerReject("identity mismatch")
    if card.get("stored_prose") not in (0, None):
        raise LayerReject("stored prose")
    if not isinstance(card.get("bound"), int) or not 1 <= card["bound"] <= 1024:
        raise LayerReject("bound")
    value = card.get(KEY)
    if value in (None, "", [], {}):
        raise LayerReject("missing:" + KEY)
    if isinstance(value, int) and (value > card["bound"] or value < 0):
        raise LayerReject("over bound")
    if FINALITY and card.get("finality") != LAYER_ID:
        raise LayerReject("finality")
    if card.get("ordinal") not in (None, ORDINAL):
        raise LayerReject("ordinal")
    body = {"layer": LAYER_ID, "key": KEY, "bound": card["bound"]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"layer": LAYER_ID, "key": KEY, "ordinal": ORDINAL, "digest": digest, "admitted": True, "stored_prose": 0}
