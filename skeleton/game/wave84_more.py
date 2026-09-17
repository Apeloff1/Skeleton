"""Second wave-84 pass. Extra through + cope."""

from __future__ import annotations

from typing import Any

from skeleton.game.cope_pack import set_cope
from skeleton.game.seal_card import seal
from skeleton.game.throughstone_pack import set_thru


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_thru({"throughstone": []}, "ts_01")
    state = set_cope(state, "cp_01")
    return seal({
        "kind": "wave84_more",
        "seed": int(seed),
        "throughstone": int(bool(state.get("throughstone"))),
        "cope": state.get("cope"),
        "sota_ready": False,
        "stored_prose": 0,
    })
