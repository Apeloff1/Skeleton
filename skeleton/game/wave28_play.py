"""Wave-28 play. Ash, lye, tallow, cake."""

from __future__ import annotations

from typing import Any

from skeleton.game.ash_pack import sift
from skeleton.game.cake_pack import cut
from skeleton.game.lye_pack import leach
from skeleton.game.seal_card import seal
from skeleton.game.tallow_pack import render
from skeleton.game.wave28_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = sift({"ash": [], "cake": [], "wet": 0, "heat": 6}, "as_00")
    state = leach(state, "ly_00")
    state = render(state, "tl_00")
    state = cut(state, "ck_00")
    info = census()
    return seal({
        "kind": "wave28_play",
        "seed": int(seed),
        "packs": info["n"],
        "ash": int(bool(state.get("ash"))),
        "lye": state.get("lye"),
        "cake": int(bool(state.get("cake"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
