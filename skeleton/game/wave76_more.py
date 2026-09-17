"""Second wave-76 pass. Extra must + lees."""

from __future__ import annotations

from typing import Any

from skeleton.game.lees_pack import rack
from skeleton.game.must_pack import press
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = press({"wet": 0}, "mu_01")
    state = rack(state, "le_01")
    return seal({
        "kind": "wave76_more",
        "seed": int(seed),
        "wet": state.get("wet"),
        "clear": state.get("clear"),
        "sota_ready": False,
        "stored_prose": 0,
    })
