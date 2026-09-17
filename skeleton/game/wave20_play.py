"""Wave-20 play. Churn, curd, whey, cheese."""

from __future__ import annotations

from typing import Any

from skeleton.game.cheese_pack import age
from skeleton.game.churn_pack import beat
from skeleton.game.curd_pack import set_curd
from skeleton.game.seal_card import seal
from skeleton.game.wave20_index import census
from skeleton.game.whey_pack import drain


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = beat({"butter": 0, "curd": [], "cheese": [], "wet": 0}, "cn_00")
    state = set_curd(state, "cd_00")
    state = drain(state, "wy_00")
    state = age(state, "ch_00")
    info = census()
    return seal({
        "kind": "wave20_play",
        "seed": int(seed),
        "packs": info["n"],
        "butter": state.get("butter"),
        "curd": int(bool(state.get("curd"))),
        "cheese": int(bool(state.get("cheese"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
