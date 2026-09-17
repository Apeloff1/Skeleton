"""Wave-44 play. Capstan, windlass, pawl, barrel."""

from __future__ import annotations

from typing import Any

from skeleton.game.barrel_pack import set_barrel
from skeleton.game.capstan_pack import heave
from skeleton.game.pawl_pack import lock
from skeleton.game.seal_card import seal
from skeleton.game.wave44_index import census
from skeleton.game.windlass_pack import crank


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = heave({"turns": 0, "rode": 0}, "cp_00")
    state = crank(state, "wd_00")
    state = lock(state, "pw_00")
    state = set_barrel(state, "bl_00")
    info = census()
    return seal({
        "kind": "wave44_play",
        "seed": int(seed),
        "packs": info["n"],
        "turns": state.get("turns"),
        "rode": state.get("rode"),
        "locked": state.get("locked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
