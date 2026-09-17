"""Wave-69 play. Hook, blade, swath, stook."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.sickleblade_pack import set_blade
from skeleton.game.sicklehook_pack import set_hook
from skeleton.game.stook_pack import stack
from skeleton.game.swath_pack import lay
from skeleton.game.wave69_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_hook({"cut": 0, "swath": [], "stook": []}, "sk_00")
    state = set_blade(state, "sb_00")
    state = lay(state, "sw_00")
    state = stack(state, "st_00")
    info = census()
    return seal({
        "kind": "wave69_play",
        "seed": int(seed),
        "packs": info["n"],
        "cut": state.get("cut"),
        "swath": int(bool(state.get("swath"))),
        "stook": int(bool(state.get("stook"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
