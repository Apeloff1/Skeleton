"""Wave-48 play. Globe, chimney, oil, trim."""

from __future__ import annotations

from typing import Any

from skeleton.game.chimney_pack import set_chimney
from skeleton.game.globe_pack import set_globe
from skeleton.game.oilpot_pack import fill
from skeleton.game.seal_card import seal
from skeleton.game.wave48_index import census
from skeleton.game.wicktrim_pack import trim


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_globe({"light": 0}, "gb_00")
    node = set_chimney(node, "ch_00")
    state = fill(node, "op_00", 4)
    state = trim(state, "wt_00")
    info = census()
    return seal({
        "kind": "wave48_play",
        "seed": int(seed),
        "packs": info["n"],
        "globe": state.get("globe"),
        "oil": state.get("oil"),
        "light": state.get("light"),
        "sota_ready": False,
        "stored_prose": 0,
    })
