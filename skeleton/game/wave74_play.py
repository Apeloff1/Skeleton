"""Wave-74 play. Steep, floor, kiln, grist."""

from __future__ import annotations

from typing import Any

from skeleton.game.grist_pack import mill
from skeleton.game.kilnmalt_pack import dry
from skeleton.game.maltfloor_pack import turn
from skeleton.game.maltsteep_pack import soak
from skeleton.game.seal_card import seal
from skeleton.game.wave74_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = soak({"wet": 0, "turn": 0, "heat": 6, "grist": []}, "mt_00")
    state = turn(state, "mf_00")
    state = dry(state, "km_00")
    state = mill(state, "gr_00")
    info = census()
    return seal({
        "kind": "wave74_play",
        "seed": int(seed),
        "packs": info["n"],
        "wet": state.get("wet"),
        "turn": state.get("turn"),
        "grist": int(bool(state.get("grist"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
