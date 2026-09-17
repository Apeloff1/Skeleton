"""Wave-70 play. Floor, aisle, bay, mow."""

from __future__ import annotations

from typing import Any

from skeleton.game.aisle_pack import set_aisle
from skeleton.game.barnbay_pack import set_bay
from skeleton.game.haymow_pack import set_mow
from skeleton.game.seal_card import seal
from skeleton.game.threshfloor_pack import set_floor
from skeleton.game.wave70_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_floor({}, "tf_00")
    node = set_aisle(node, "ai_00")
    node = set_bay(node, "bb_00")
    node = set_mow(node, "hm_00", 6)
    info = census()
    return seal({
        "kind": "wave70_play",
        "seed": int(seed),
        "packs": info["n"],
        "threshfloor": node.get("threshfloor"),
        "barnbay": node.get("barnbay"),
        "hay": node.get("hay"),
        "sota_ready": False,
        "stored_prose": 0,
    })
