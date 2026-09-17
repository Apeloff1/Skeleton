"""Wave-41 play. Sheave, tackle, stay, shroud."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.sheave_pack import set_sheave
from skeleton.game.shroud_pack import set_shroud
from skeleton.game.stayline_pack import set_stay
from skeleton.game.tackle_pack import haul
from skeleton.game.wave41_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_sheave({"load": 0}, "sv_00")
    state = haul(state, "tk_00")
    node = set_stay({}, "st_00")
    node = set_shroud(node, "sh_00")
    info = census()
    return seal({
        "kind": "wave41_play",
        "seed": int(seed),
        "packs": info["n"],
        "sheave": state.get("sheave"),
        "load": state.get("load"),
        "stay": node.get("stay"),
        "sota_ready": False,
        "stored_prose": 0,
    })
