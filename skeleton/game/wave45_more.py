"""Second wave-45 pass. Extra fluke + ring."""

from __future__ import annotations

from typing import Any

from skeleton.game.fluke_pack import set_fluke
from skeleton.game.ringeye_pack import set_ring
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_fluke({"hold": 0}, "fk_01")
    state = set_ring(state, "re_01")
    return seal({
        "kind": "wave45_more",
        "seed": int(seed),
        "hold": state.get("hold"),
        "ringeye": state.get("ringeye"),
        "sota_ready": False,
        "stored_prose": 0,
    })
