"""Wave-75 play. Wash, retort, worm, foreshot."""

from __future__ import annotations

from typing import Any

from skeleton.game.foreshot_pack import cut
from skeleton.game.retort_pack import heat
from skeleton.game.seal_card import seal
from skeleton.game.wave75_index import census
from skeleton.game.wash_pack import charge
from skeleton.game.wormcoil_pack import set_worm


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = charge({"wet": 0, "heat": 6, "cool": 0, "cut": 0}, "wa_00")
    state = heat(state, "rt_00")
    state = set_worm(state, "wc_00")
    state = cut(state, "fs_00")
    info = census()
    return seal({
        "kind": "wave75_play",
        "seed": int(seed),
        "packs": info["n"],
        "wash": state.get("wash"),
        "cool": state.get("cool"),
        "cut": state.get("cut"),
        "sota_ready": False,
        "stored_prose": 0,
    })
