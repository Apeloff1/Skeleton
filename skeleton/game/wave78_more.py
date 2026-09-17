"""Second wave-78 pass. Extra super + puff."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.smoker_pack import puff
from skeleton.game.supers_pack import add


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = add({"supers": []}, "su_01")
    state = puff(state, "sm_01")
    return seal({
        "kind": "wave78_more",
        "seed": int(seed),
        "supers": int(bool(state.get("supers"))),
        "calm": state.get("calm"),
        "sota_ready": False,
        "stored_prose": 0,
    })
