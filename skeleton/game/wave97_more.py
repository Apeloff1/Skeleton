"""Second wave-97 pass. Extra roll + letters."""

from __future__ import annotations

from typing import Any

from skeleton.game.letters_pack import issue
from skeleton.game.roll_pack import enter
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = enter({"roll": []}, "rl_01")
    state = issue(state, "lp_01")
    return seal({
        "kind": "wave97_more",
        "seed": int(seed),
        "roll": int(bool(state.get("roll"))),
        "issued": state.get("issued"),
        "sota_ready": False,
        "stored_prose": 0,
    })
