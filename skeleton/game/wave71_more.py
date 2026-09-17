"""Second wave-71 pass. Extra cream + rennet."""

from __future__ import annotations

from typing import Any

from skeleton.game.cream_pack import skim
from skeleton.game.rennet_pack import add
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = skim({"fat": 0}, "cr_01")
    state = add(state, "rn_01")
    return seal({
        "kind": "wave71_more",
        "seed": int(seed),
        "fat": state.get("fat"),
        "set": state.get("set"),
        "sota_ready": False,
        "stored_prose": 0,
    })
