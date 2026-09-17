"""Second wave-38 pass. Extra chain + sight."""

from __future__ import annotations

from typing import Any

from skeleton.game.chain_pack import stretch
from skeleton.game.seal_card import seal
from skeleton.game.theo_pack import sight


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = stretch({}, "cn_01", 33)
    state = sight(state, "th_01", 180)
    return seal({
        "kind": "wave38_more",
        "seed": int(seed),
        "len": state.get("len"),
        "az": state.get("az"),
        "sota_ready": False,
        "stored_prose": 0,
    })
