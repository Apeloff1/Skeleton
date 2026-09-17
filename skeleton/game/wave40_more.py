"""Second wave-40 pass. Extra cringle + reef."""

from __future__ import annotations

from typing import Any

from skeleton.game.cringle_pack import set_cringle
from skeleton.game.reef_pack import take
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_cringle({"cringle": [], "area": 8}, "cg_01")
    state = take(state, "rf_01")
    return seal({
        "kind": "wave40_more",
        "seed": int(seed),
        "cringle": int(bool(state.get("cringle"))),
        "area": state.get("area"),
        "sota_ready": False,
        "stored_prose": 0,
    })
