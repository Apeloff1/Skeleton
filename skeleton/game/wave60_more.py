"""Second wave-60 pass. Extra axle + pin."""

from __future__ import annotations

from typing import Any

from skeleton.game.cartaxle_pack import set_axle
from skeleton.game.linchpin_pack import set_pin
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_axle({}, "ax_01")
    state = set_pin(state, "lp_01")
    return seal({
        "kind": "wave60_more",
        "seed": int(seed),
        "cartaxle": state.get("cartaxle"),
        "locked": state.get("locked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
