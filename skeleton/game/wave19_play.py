"""Wave-19 play. Mill, hopper, grind, sack."""

from __future__ import annotations

from typing import Any

from skeleton.game.flour_pack import grind
from skeleton.game.hopper_pack import load
from skeleton.game.mill_pack import set_mill
from skeleton.game.sack_pack import fill
from skeleton.game.seal_card import seal
from skeleton.game.wave19_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_mill({}, "ml_00")
    state = load({"grain": 0, "flour": [], "sack": []}, "hp_00", 2)
    state = grind(state, "fl_00")
    state = fill(state, "sk_00")
    info = census()
    return seal({
        "kind": "wave19_play",
        "seed": int(seed),
        "packs": info["n"],
        "mill": node.get("mill"),
        "flour": int(bool(state.get("flour"))),
        "sack": int(bool(state.get("sack"))),
        "grain": state.get("grain"),
        "sota_ready": False,
        "stored_prose": 0,
    })
