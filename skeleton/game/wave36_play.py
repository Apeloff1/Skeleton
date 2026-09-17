"""Wave-36 play. Hardy, fuller, swage, drift."""

from __future__ import annotations

from typing import Any

from skeleton.game.drift_pack import punch
from skeleton.game.fuller_pack import groove
from skeleton.game.hardy_pack import cut
from skeleton.game.seal_card import seal
from skeleton.game.swage_pack import form
from skeleton.game.wave36_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = cut({"scrap": 0, "hole": 0}, "hy_00")
    state = groove(state, "fu_00")
    state = form(state, "sw_00")
    state = punch(state, "dr_00")
    info = census()
    return seal({
        "kind": "wave36_play",
        "seed": int(seed),
        "packs": info["n"],
        "hardy": state.get("hardy"),
        "scrap": state.get("scrap"),
        "hole": state.get("hole"),
        "sota_ready": False,
        "stored_prose": 0,
    })
