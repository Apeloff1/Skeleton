"""Second wave-69 pass. Extra swath + stook."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.stook_pack import stack
from skeleton.game.swath_pack import lay


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = lay({"swath": [], "stook": []}, "sw_01")
    state = stack(state, "st_01")
    return seal({
        "kind": "wave69_more",
        "seed": int(seed),
        "swath": int(bool(state.get("swath"))),
        "stook": int(bool(state.get("stook"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
