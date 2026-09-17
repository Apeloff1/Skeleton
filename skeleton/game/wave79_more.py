"""Second wave-79 pass. Extra line + creel."""

from __future__ import annotations

from typing import Any

from skeleton.game.creel_pack import fill
from skeleton.game.longline_pack import set_line
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_line({}, "ll_01", 20)
    state = fill(state, "cr_01", 3)
    return seal({
        "kind": "wave79_more",
        "seed": int(seed),
        "hooks": state.get("hooks"),
        "catch": state.get("catch"),
        "sota_ready": False,
        "stored_prose": 0,
    })
