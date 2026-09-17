"""Second wave-47 pass. Extra drain."""

from __future__ import annotations

from typing import Any

from skeleton.game.bilge_pack import set_bilge
from skeleton.game.limber_pack import drain
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_bilge({}, "bg_01", 3)
    node = drain(node, "lm_01")
    return seal({
        "kind": "wave47_more",
        "seed": int(seed),
        "water": node.get("water"),
        "limber": node.get("limber"),
        "sota_ready": False,
        "stored_prose": 0,
    })
