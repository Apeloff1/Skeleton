"""Second wave-24 pass. Extra rick + faggot."""

from __future__ import annotations

from typing import Any

from skeleton.game.faggot_pack import bind
from skeleton.game.rick_pack import stack
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = stack({"rick": [], "faggot": []}, "rk_01")
    state = bind(state, "fg_01")
    return seal({
        "kind": "wave24_more",
        "seed": int(seed),
        "rick": int(bool(state.get("rick"))),
        "faggot": int(bool(state.get("faggot"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
