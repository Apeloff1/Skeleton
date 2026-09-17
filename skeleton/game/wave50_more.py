"""Second wave-50 pass. Extra hew + bung."""

from __future__ import annotations

from typing import Any

from skeleton.game.adze_pack import hew
from skeleton.game.bung_pack import set_bung
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = hew({"hewn": 0}, "az_01")
    state = set_bung(state, "bg_01")
    return seal({
        "kind": "wave50_more",
        "seed": int(seed),
        "hewn": state.get("hewn"),
        "sealed": state.get("sealed"),
        "sota_ready": False,
        "stored_prose": 0,
    })
