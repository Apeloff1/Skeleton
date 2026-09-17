"""Second wave-94 pass. Extra yard + perch."""

from __future__ import annotations

from typing import Any

from skeleton.game.perch_pack import measure as perch_m
from skeleton.game.seal_card import seal
from skeleton.game.yardstick_pack import measure as yard_m


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = yard_m({}, "yd_01", 5)
    state = perch_m(state, "pe_01", 2)
    return seal({
        "kind": "wave94_more",
        "seed": int(seed),
        "yd": state.get("yd"),
        "rd": state.get("rd"),
        "sota_ready": False,
        "stored_prose": 0,
    })
