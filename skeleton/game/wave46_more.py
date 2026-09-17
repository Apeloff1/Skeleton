"""Second wave-46 pass. Extra lid + belay."""

from __future__ import annotations

from typing import Any

from skeleton.game.cleatpin_pack import belay
from skeleton.game.hatchlid_pack import set_lid
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_lid({}, "hl_01", 1)
    state = belay(node, "cl_01")
    return seal({
        "kind": "wave46_more",
        "seed": int(seed),
        "open": state.get("open"),
        "belay": state.get("belay"),
        "sota_ready": False,
        "stored_prose": 0,
    })
