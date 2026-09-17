"""Second wave-74 pass. Extra steep + grist."""

from __future__ import annotations

from typing import Any

from skeleton.game.grist_pack import mill
from skeleton.game.maltsteep_pack import soak
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = soak({"wet": 0, "grist": []}, "mt_01")
    state = mill(state, "gr_01")
    return seal({
        "kind": "wave74_more",
        "seed": int(seed),
        "wet": state.get("wet"),
        "grist": int(bool(state.get("grist"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
