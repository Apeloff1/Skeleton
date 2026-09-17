"""Second wave-87 pass. Extra step + pack."""

from __future__ import annotations

from typing import Any

from skeleton.game.packhorse_pack import load
from skeleton.game.seal_card import seal
from skeleton.game.stepstone_pack import set_step


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_step({"stepstone": []}, "ss_01")
    state = load(node, "ph_01", 2)
    return seal({
        "kind": "wave87_more",
        "seed": int(seed),
        "stepstone": int(bool(state.get("stepstone"))),
        "load": state.get("load"),
        "sota_ready": False,
        "stored_prose": 0,
    })
