"""Second wave-36 pass. Extra hardy + drift."""

from __future__ import annotations

from typing import Any

from skeleton.game.drift_pack import punch
from skeleton.game.hardy_pack import cut
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = cut({"scrap": 0, "hole": 0}, "hy_01")
    state = punch(state, "dr_01")
    return seal({
        "kind": "wave36_more",
        "seed": int(seed),
        "scrap": state.get("scrap"),
        "hole": state.get("hole"),
        "sota_ready": False,
        "stored_prose": 0,
    })
