"""Second wave-54 pass. Extra ward + lift."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.tumbler_pack import lift
from skeleton.game.ward_pack import set_ward


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_ward({"ward": [], "lift": 0}, "wd_01")
    state = lift(state, "tb_01")
    return seal({
        "kind": "wave54_more",
        "seed": int(seed),
        "ward": int(bool(state.get("ward"))),
        "lift": state.get("lift"),
        "sota_ready": False,
        "stored_prose": 0,
    })
