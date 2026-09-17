"""Second wave-15 pass. Heddle, reed."""

from __future__ import annotations

from typing import Any

from skeleton.game.heddle_pack import lift
from skeleton.game.reed_pack import beat
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = lift({}, "hd_00")
    state = beat({"picks": 1}, "rd_00")
    return seal({
        "kind": "wave15_more",
        "seed": int(seed),
        "heddle": node.get("heddle"),
        "shed": node.get("shed"),
        "reed": state.get("reed"),
        "sota_ready": False,
        "stored_prose": 0,
    })
