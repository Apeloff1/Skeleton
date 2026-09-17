"""Second wave-98 pass. Extra plea + writ."""

from __future__ import annotations

from typing import Any

from skeleton.game.plea_pack import enter
from skeleton.game.seal_card import seal
from skeleton.game.writ_pack import issue


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = enter({}, "pl_01")
    state = issue(state, "wr_01")
    return seal({
        "kind": "wave98_more",
        "seed": int(seed),
        "entered": state.get("entered"),
        "issued": state.get("issued"),
        "sota_ready": False,
        "stored_prose": 0,
    })
