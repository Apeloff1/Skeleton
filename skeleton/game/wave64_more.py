"""Second wave-64 pass. Extra staff + swipple."""

from __future__ import annotations

from typing import Any

from skeleton.game.handstaff_pack import set_staff
from skeleton.game.seal_card import seal
from skeleton.game.swipple_pack import set_swipple


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_staff({"beat": 0}, "hs_01")
    state = set_swipple(state, "sw_01")
    return seal({
        "kind": "wave64_more",
        "seed": int(seed),
        "handstaff": state.get("handstaff"),
        "beat": state.get("beat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
