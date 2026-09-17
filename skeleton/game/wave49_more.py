"""Second wave-49 pass. Extra haul + fly."""

from __future__ import annotations

from typing import Any

from skeleton.game.fly_pack import set_fly
from skeleton.game.halliard_pack import haul
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = haul({}, "ha_01")
    state = set_fly(state, "fy_01", 6)
    return seal({
        "kind": "wave49_more",
        "seed": int(seed),
        "up": state.get("up"),
        "span": state.get("span"),
        "sota_ready": False,
        "stored_prose": 0,
    })
