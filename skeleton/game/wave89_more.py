"""Second wave-89 pass. Extra stall + cry."""

from __future__ import annotations

from typing import Any

from skeleton.game.cryer_pack import cry
from skeleton.game.marketstall_pack import set_stall
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_stall({}, "ms_01")
    state = cry(node, "cy_01")
    return seal({
        "kind": "wave89_more",
        "seed": int(seed),
        "marketstall": state.get("marketstall"),
        "heard": state.get("heard"),
        "sota_ready": False,
        "stored_prose": 0,
    })
