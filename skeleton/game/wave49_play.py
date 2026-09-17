"""Wave-49 play. Truck, halliard, hoist, fly."""

from __future__ import annotations

from typing import Any

from skeleton.game.fly_pack import set_fly
from skeleton.game.halliard_pack import haul
from skeleton.game.hoistlen_pack import set_hoist
from skeleton.game.seal_card import seal
from skeleton.game.truck_pack import set_truck
from skeleton.game.wave49_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_truck({}, "tr_00")
    state = haul(node, "ha_00")
    state = set_hoist(state, "hs_00", 8)
    state = set_fly(state, "fy_00", 12)
    info = census()
    return seal({
        "kind": "wave49_play",
        "seed": int(seed),
        "packs": info["n"],
        "up": state.get("up"),
        "hoist": state.get("hoist"),
        "span": state.get("span"),
        "sota_ready": False,
        "stored_prose": 0,
    })
