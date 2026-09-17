"""Second wave-43 pass. Extra oakum + drive."""

from __future__ import annotations

from typing import Any

from skeleton.game.caulkiron_pack import drive
from skeleton.game.oakum_pack import take
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = take({"oakum": [], "driven": 0}, "ok_01")
    state = drive(state, "ci_01")
    return seal({
        "kind": "wave43_more",
        "seed": int(seed),
        "oakum": int(bool(state.get("oakum"))),
        "driven": state.get("driven"),
        "sota_ready": False,
        "stored_prose": 0,
    })
