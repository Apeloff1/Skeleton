"""CS300-238 complete build. No delegate. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

LAYER_ID = "CS300-238"
KEY = "data_locality_scheduler"
ORDINAL = 238
FINALITY = False
CASES = ("normal", "adversarial", "boundary", "failure", "recovery")


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
    if not isinstance(bound, int) or not 1 <= bound <= 1024:
        raise LayerReject("bound")
    cases = card.get("cases")
    if not isinstance(cases, dict) or set(cases) != set(CASES):
        raise LayerReject("cases")
    normal = cases["normal"].get(KEY)
    if not isinstance(normal, int) or normal < 0 or normal > bound:
        raise LayerReject("normal")
    if cases["adversarial"].get("accepted") is not False:
        raise LayerReject("adversarial")
    if cases["boundary"].get("at_bound") is not True:
        raise LayerReject("boundary")
    failure = cases["failure"]
    if failure.get("failed") is not True or failure.get("opened") is not False:
        raise LayerReject("failure")
    recovery = cases["recovery"]
    if recovery.get("restored") is not True or recovery.get("generation") != ORDINAL:
        raise LayerReject("recovery")
    if FINALITY and card.get("finality") != LAYER_ID:
        raise LayerReject("finality")
    cost = normal + ORDINAL
    if cost > bound + ORDINAL:
        raise LayerReject("cost")
    body = {"layer": LAYER_ID, "key": KEY, "cost": cost, "generation": ORDINAL}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "layer": LAYER_ID,
        "key": KEY,
        "ordinal": ORDINAL,
        "cost": cost,
        "generation": recovery["generation"],
        "digest": digest,
        "cases": list(CASES),
        "built": True,
        "stub": False,
        "stored_prose": 0,
    }
