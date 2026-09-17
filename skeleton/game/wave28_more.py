"""Second wave-28 pass. Extra ash + cake."""

from __future__ import annotations

from typing import Any

from skeleton.game.ash_pack import sift
from skeleton.game.cake_pack import cut
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = sift({"ash": [], "cake": []}, "as_01")
    state = cut(state, "ck_01")
    return seal({
        "kind": "wave28_more",
        "seed": int(seed),
        "ash": int(bool(state.get("ash"))),
        "cake": int(bool(state.get("cake"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
