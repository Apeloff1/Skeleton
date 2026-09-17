"""Wave-91 play. Touch, assay, carat, hallmark."""

from __future__ import annotations

from typing import Any

from skeleton.game.assay_pack import test
from skeleton.game.carat_pack import set_carat
from skeleton.game.hallmark_pack import punch
from skeleton.game.seal_card import seal
from skeleton.game.touchstone_pack import streak
from skeleton.game.wave91_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = streak({}, "ts_00")
    state = test(state, "as_00")
    state = set_carat(state, "ct_00", 18)
    state = punch(state, "hm_00")
    info = census()
    return seal({
        "kind": "wave91_play",
        "seed": int(seed),
        "packs": info["n"],
        "tested": state.get("tested"),
        "kt": state.get("kt"),
        "marked": state.get("marked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
