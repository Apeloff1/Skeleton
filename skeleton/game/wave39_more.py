"""Second wave-39 pass. Extra shoot + cast."""

from __future__ import annotations

from typing import Any

from skeleton.game.leadline_pack import cast
from skeleton.game.seal_card import seal
from skeleton.game.sextant_pack import shoot


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = shoot({}, "sx_01", 18)
    state = cast(state, "ld_01", 8)
    return seal({
        "kind": "wave39_more",
        "seed": int(seed),
        "alt": state.get("alt"),
        "fath": state.get("fath"),
        "sota_ready": False,
        "stored_prose": 0,
    })
