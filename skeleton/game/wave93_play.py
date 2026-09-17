"""Wave-93 play. Yard, fulcrum, poise, pan."""

from __future__ import annotations

from typing import Any

from skeleton.game.fulcrum_pack import set_fulc
from skeleton.game.poise_pack import slide
from skeleton.game.seal_card import seal
from skeleton.game.steelyard_pack import set_yard
from skeleton.game.wave93_index import census
from skeleton.game.weightpan_pack import set_pan


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_yard({}, "sy_00")
    state = set_fulc(state, "fu_00")
    state = slide(state, "po_00", 6)
    state = set_pan(state, "wp_00", 8)
    info = census()
    return seal({
        "kind": "wave93_play",
        "seed": int(seed),
        "packs": info["n"],
        "steelyard": state.get("steelyard"),
        "arm": state.get("arm"),
        "load": state.get("load"),
        "sota_ready": False,
        "stored_prose": 0,
    })
