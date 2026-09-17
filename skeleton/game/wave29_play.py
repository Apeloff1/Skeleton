"""Wave-29 play. Wick, dip, taper, snuff."""

from __future__ import annotations

from typing import Any

from skeleton.game.dip_pack import dunk
from skeleton.game.seal_card import seal
from skeleton.game.snuff_pack import pinch
from skeleton.game.taper_pack import light
from skeleton.game.wave29_index import census
from skeleton.game.wick_pack import set_wick


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_wick({"wick": [], "coat": 0, "light": 0}, "wk_00")
    state = dunk(state, "dp_00")
    state = light(state, "tp_00")
    state = pinch(state, "sn_00")
    info = census()
    return seal({
        "kind": "wave29_play",
        "seed": int(seed),
        "packs": info["n"],
        "wick": int(bool(state.get("wick"))),
        "coat": state.get("coat"),
        "light": state.get("light"),
        "sota_ready": False,
        "stored_prose": 0,
    })
