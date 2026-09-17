"""Second wave-37 pass. Extra tick + wind."""

from __future__ import annotations

from typing import Any

from skeleton.game.escape_pack import tick
from skeleton.game.fusee_pack import wind
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = tick({"tick": 0, "wind": 0}, "es_01")
    state = wind(state, "fe_01")
    return seal({
        "kind": "wave37_more",
        "seed": int(seed),
        "tick": state.get("tick"),
        "wind": state.get("wind"),
        "sota_ready": False,
        "stored_prose": 0,
    })
