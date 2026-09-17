"""Wave-38 play. Chain, rod, staff, theo."""

from __future__ import annotations

from typing import Any

from skeleton.game.chain_pack import stretch
from skeleton.game.rod_pack import set_rod
from skeleton.game.seal_card import seal
from skeleton.game.staff_pack import read
from skeleton.game.theo_pack import sight
from skeleton.game.wave38_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = stretch({}, "cn_00", 66)
    state = set_rod(state, "rd_00")
    state = read(state, "sf_00", 12)
    state = sight(state, "th_00", 90)
    info = census()
    return seal({
        "kind": "wave38_play",
        "seed": int(seed),
        "packs": info["n"],
        "len": state.get("len"),
        "level": state.get("level"),
        "az": state.get("az"),
        "sota_ready": False,
        "stored_prose": 0,
    })
