"""Wave-56 play. Nave, spoke, felloe, tyre."""

from __future__ import annotations

from typing import Any

from skeleton.game.felloe_pack import set_felloe
from skeleton.game.nave_pack import set_nave
from skeleton.game.seal_card import seal
from skeleton.game.spokeset_pack import set_spoke
from skeleton.game.tyreband_pack import shrink
from skeleton.game.wave56_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_nave({"felloe": []}, "nv_00")
    state = set_spoke(state, "sp_00", 12)
    state = set_felloe(state, "fe_00")
    state = shrink(state, "ty_00")
    info = census()
    return seal({
        "kind": "wave56_play",
        "seed": int(seed),
        "packs": info["n"],
        "nave": state.get("nave"),
        "spokes": state.get("spokes"),
        "tight": state.get("tight"),
        "sota_ready": False,
        "stored_prose": 0,
    })
