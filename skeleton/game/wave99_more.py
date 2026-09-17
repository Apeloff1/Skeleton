"""Second wave-99 pass. Extra poll + geld."""

from __future__ import annotations

from typing import Any

from skeleton.game.geld_pack import levy as geld_levy
from skeleton.game.poll_pack import count
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = count({}, "po_01", 20)
    state = geld_levy(state, "gd_01", 1)
    return seal({
        "kind": "wave99_more",
        "seed": int(seed),
        "heads": state.get("heads"),
        "due": state.get("due"),
        "sota_ready": False,
        "stored_prose": 0,
    })
