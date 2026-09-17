"""Second wave-44 pass. Extra heave + lock."""

from __future__ import annotations

from typing import Any

from skeleton.game.capstan_pack import heave
from skeleton.game.pawl_pack import lock
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = heave({"turns": 0}, "cp_01")
    state = lock(state, "pw_01")
    return seal({
        "kind": "wave44_more",
        "seed": int(seed),
        "turns": state.get("turns"),
        "locked": state.get("locked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
