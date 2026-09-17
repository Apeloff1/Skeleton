"""Second wave-27 pass. Extra indigo + madder."""

from __future__ import annotations

from typing import Any

from skeleton.game.indigo_pack import dip
from skeleton.game.madder_pack import steep
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = dip({"wet": 0}, "in_01")
    state = steep(state, "mr_01")
    return seal({
        "kind": "wave27_more",
        "seed": int(seed),
        "indigo": state.get("indigo"),
        "madder": state.get("madder"),
        "sota_ready": False,
        "stored_prose": 0,
    })
