"""Wave-16 play. Well, pump, cistern, sluice."""

from __future__ import annotations

from typing import Any

from skeleton.game.cistern_pack import fill
from skeleton.game.pump_pack import stroke
from skeleton.game.seal_card import seal
from skeleton.game.sluice_pack import set_gate
from skeleton.game.wave16_index import census
from skeleton.game.well_pack import draw


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = draw({"water": 0}, "wl_00")
    state = stroke(state, "pm_00")
    node = fill({"held": 0}, "cs_00", int(state.get("water", 0)))
    node = set_gate(node, "sl_00", 1)
    info = census()
    return seal({
        "kind": "wave16_play",
        "seed": int(seed),
        "packs": info["n"],
        "well": state.get("well"),
        "water": state.get("water"),
        "held": node.get("held"),
        "open": node.get("open"),
        "sota_ready": False,
        "stored_prose": 0,
    })
