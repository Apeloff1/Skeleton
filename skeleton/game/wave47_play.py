"""Wave-47 play. Bilge, strum, rose, limber."""

from __future__ import annotations

from typing import Any

from skeleton.game.bilge_pack import set_bilge
from skeleton.game.limber_pack import drain
from skeleton.game.rosebox_pack import set_rose
from skeleton.game.seal_card import seal
from skeleton.game.strum_pack import set_strum
from skeleton.game.wave47_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_bilge({}, "bg_00", 4)
    node = set_strum(node, "sr_00")
    node = set_rose(node, "rb_00")
    node = drain(node, "lm_00")
    info = census()
    return seal({
        "kind": "wave47_play",
        "seed": int(seed),
        "packs": info["n"],
        "bilge": node.get("bilge"),
        "water": node.get("water"),
        "limber": node.get("limber"),
        "sota_ready": False,
        "stored_prose": 0,
    })
