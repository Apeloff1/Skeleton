"""Second wave-63 pass. Extra snath + beard."""

from __future__ import annotations

from typing import Any

from skeleton.game.beard_pack import set_beard
from skeleton.game.seal_card import seal
from skeleton.game.snath_pack import set_snath


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_snath({"cut": 0}, "sn_01")
    state = set_beard(state, "bd_01")
    return seal({
        "kind": "wave63_more",
        "seed": int(seed),
        "snath": state.get("snath"),
        "cut": state.get("cut"),
        "sota_ready": False,
        "stored_prose": 0,
    })
