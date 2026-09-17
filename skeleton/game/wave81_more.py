"""Second wave-81 pass. Extra dredge + tongs."""

from __future__ import annotations

from typing import Any

from skeleton.game.dredge_pack import tow
from skeleton.game.seal_card import seal
from skeleton.game.tongs_pack import grip


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = tow({"haul": 0, "take": 0}, "dg_01")
    state = grip(state, "tg_01")
    return seal({
        "kind": "wave81_more",
        "seed": int(seed),
        "haul": state.get("haul"),
        "take": state.get("take"),
        "sota_ready": False,
        "stored_prose": 0,
    })
