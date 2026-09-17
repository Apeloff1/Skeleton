"""Second wave-48 pass. Extra oil + trim."""

from __future__ import annotations

from typing import Any

from skeleton.game.oilpot_pack import fill
from skeleton.game.seal_card import seal
from skeleton.game.wicktrim_pack import trim


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = fill({"light": 0}, "op_01", 2)
    state = trim(state, "wt_01")
    return seal({
        "kind": "wave48_more",
        "seed": int(seed),
        "oil": state.get("oil"),
        "light": state.get("light"),
        "sota_ready": False,
        "stored_prose": 0,
    })
