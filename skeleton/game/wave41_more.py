"""Second wave-41 pass. Extra haul + stay."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.stayline_pack import set_stay
from skeleton.game.tackle_pack import haul


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = haul({"load": 0}, "tk_01")
    node = set_stay({}, "st_01")
    return seal({
        "kind": "wave41_more",
        "seed": int(seed),
        "load": state.get("load"),
        "stay": node.get("stay"),
        "sota_ready": False,
        "stored_prose": 0,
    })
