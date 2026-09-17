"""Second wave-51 pass. Extra shoe + tap."""

from __future__ import annotations

from typing import Any

from skeleton.game.damsel_pack import tap
from skeleton.game.seal_card import seal
from skeleton.game.shoe_pack import set_shoe


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_shoe({"tap": 0}, "sh_01", 1)
    state = tap(node, "dm_01")
    return seal({
        "kind": "wave51_more",
        "seed": int(seed),
        "feed": state.get("feed"),
        "tap": state.get("tap"),
        "sota_ready": False,
        "stored_prose": 0,
    })
