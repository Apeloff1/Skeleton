"""Wave-60 play. Axle, reach, bolster, linchpin."""

from __future__ import annotations

from typing import Any

from skeleton.game.bolster_pack import set_bolster
from skeleton.game.cartaxle_pack import set_axle
from skeleton.game.linchpin_pack import set_pin
from skeleton.game.reach_pack import set_reach
from skeleton.game.seal_card import seal
from skeleton.game.wave60_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_axle({}, "ax_00")
    state = set_reach(state, "rc_00", 8)
    state = set_bolster(state, "bo_00")
    state = set_pin(state, "lp_00")
    info = census()
    return seal({
        "kind": "wave60_play",
        "seed": int(seed),
        "packs": info["n"],
        "cartaxle": state.get("cartaxle"),
        "len": state.get("len"),
        "locked": state.get("locked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
