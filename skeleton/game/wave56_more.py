"""Second wave-56 pass. Extra spoke + tyre."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.spokeset_pack import set_spoke
from skeleton.game.tyreband_pack import shrink


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_spoke({}, "sp_01", 10)
    state = shrink(state, "ty_01")
    return seal({
        "kind": "wave56_more",
        "seed": int(seed),
        "spokes": state.get("spokes"),
        "tight": state.get("tight"),
        "sota_ready": False,
        "stored_prose": 0,
    })
