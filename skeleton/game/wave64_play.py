"""Wave-64 play. Staff, cap, thong, swipple."""

from __future__ import annotations

from typing import Any

from skeleton.game.flailcap_pack import set_cap
from skeleton.game.handstaff_pack import set_staff
from skeleton.game.seal_card import seal
from skeleton.game.swipple_pack import set_swipple
from skeleton.game.thong_pack import set_thong
from skeleton.game.wave64_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_staff({"beat": 0}, "hs_00")
    state = set_cap(state, "fc_00")
    state = set_thong(state, "th_00")
    state = set_swipple(state, "sw_00")
    info = census()
    return seal({
        "kind": "wave64_play",
        "seed": int(seed),
        "packs": info["n"],
        "handstaff": state.get("handstaff"),
        "thong": state.get("thong"),
        "beat": state.get("beat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
