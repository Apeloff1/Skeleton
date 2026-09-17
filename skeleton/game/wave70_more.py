"""Second wave-70 pass. Extra bay + mow."""

from __future__ import annotations

from typing import Any

from skeleton.game.barnbay_pack import set_bay
from skeleton.game.haymow_pack import set_mow
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_bay({}, "bb_01")
    node = set_mow(node, "hm_01", 3)
    return seal({
        "kind": "wave70_more",
        "seed": int(seed),
        "barnbay": node.get("barnbay"),
        "hay": node.get("hay"),
        "sota_ready": False,
        "stored_prose": 0,
    })
