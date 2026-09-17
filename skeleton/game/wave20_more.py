"""Second wave-20 pass. Extra curd + cheese."""

from __future__ import annotations

from typing import Any

from skeleton.game.cheese_pack import age
from skeleton.game.curd_pack import set_curd
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_curd({"curd": [], "cheese": []}, "cd_01")
    state = age(state, "ch_01")
    return seal({
        "kind": "wave20_more",
        "seed": int(seed),
        "curd": int(bool(state.get("curd"))),
        "cheese": int(bool(state.get("cheese"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
