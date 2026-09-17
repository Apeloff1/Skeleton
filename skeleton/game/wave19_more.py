"""Second wave-19 pass. Extra grind + sack."""

from __future__ import annotations

from typing import Any

from skeleton.game.flour_pack import grind
from skeleton.game.hopper_pack import load
from skeleton.game.sack_pack import fill
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = load({"grain": 0, "flour": [], "sack": []}, "hp_01", 1)
    state = grind(state, "fl_01")
    state = fill(state, "sk_01")
    return seal({
        "kind": "wave19_more",
        "seed": int(seed),
        "flour": int(bool(state.get("flour"))),
        "sack": int(bool(state.get("sack"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
