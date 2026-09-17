"""Second wave-29 pass. Extra wick + taper."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.taper_pack import light
from skeleton.game.wick_pack import set_wick


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_wick({"wick": [], "light": 0}, "wk_01")
    state = light(state, "tp_01")
    return seal({
        "kind": "wave29_more",
        "seed": int(seed),
        "wick": int(bool(state.get("wick"))),
        "light": state.get("light"),
        "sota_ready": False,
        "stored_prose": 0,
    })
