"""Wave-59 play. Pick, rasp, nail, clinch."""

from __future__ import annotations

from typing import Any

from skeleton.game.clinch_pack import bend
from skeleton.game.hoofpick_pack import clean
from skeleton.game.nailset_pack import drive
from skeleton.game.rasphorse_pack import rasp
from skeleton.game.seal_card import seal
from skeleton.game.wave59_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = clean({"trim": 0, "set": 0, "nailset": []}, "hp_00")
    state = rasp(state, "rh_00")
    state = drive(state, "ns_00")
    state = bend(state, "cl_00")
    info = census()
    return seal({
        "kind": "wave59_play",
        "seed": int(seed),
        "packs": info["n"],
        "clean": state.get("clean"),
        "trim": state.get("trim"),
        "set": state.get("set"),
        "sota_ready": False,
        "stored_prose": 0,
    })
