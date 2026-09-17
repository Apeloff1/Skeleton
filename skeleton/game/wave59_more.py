"""Second wave-59 pass. Extra rasp + clinch."""

from __future__ import annotations

from typing import Any

from skeleton.game.clinch_pack import bend
from skeleton.game.rasphorse_pack import rasp
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = rasp({"trim": 0, "set": 0}, "rh_01")
    state = bend(state, "cl_01")
    return seal({
        "kind": "wave59_more",
        "seed": int(seed),
        "trim": state.get("trim"),
        "set": state.get("set"),
        "sota_ready": False,
        "stored_prose": 0,
    })
