"""Second wave-30 pass. Extra pulp + couch."""

from __future__ import annotations

from typing import Any

from skeleton.game.couch_pack import turn
from skeleton.game.pulp_pack import beat
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = beat({"wet": 0, "sheet": 0}, "pu_01")
    state = turn(state, "ch_01")
    return seal({
        "kind": "wave30_more",
        "seed": int(seed),
        "pulp": state.get("pulp"),
        "sheet": state.get("sheet"),
        "sota_ready": False,
        "stored_prose": 0,
    })
