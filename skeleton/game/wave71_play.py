"""Wave-71 play. Separator, cream, buttermilk, rennet."""

from __future__ import annotations

from typing import Any

from skeleton.game.buttermilk_pack import drain
from skeleton.game.cream_pack import skim
from skeleton.game.rennet_pack import add
from skeleton.game.seal_card import seal
from skeleton.game.separator_pack import spin
from skeleton.game.wave71_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = spin({"fat": 0, "wet": 0}, "sp_00")
    state = skim(state, "cr_00")
    state = drain(state, "bm_00")
    state = add(state, "rn_00")
    info = census()
    return seal({
        "kind": "wave71_play",
        "seed": int(seed),
        "packs": info["n"],
        "spin": state.get("spin"),
        "fat": state.get("fat"),
        "set": state.get("set"),
        "sota_ready": False,
        "stored_prose": 0,
    })
