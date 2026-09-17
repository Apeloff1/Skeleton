"""Second wave-53 pass. Extra heave + mark."""

from __future__ import annotations

from typing import Any

from skeleton.game.handlead_pack import heave
from skeleton.game.seal_card import seal
from skeleton.game.soundmark_pack import read


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = heave({"cast": 0}, "hd_01")
    state = read(state, "mk_01", 7)
    return seal({
        "kind": "wave53_more",
        "seed": int(seed),
        "cast": state.get("cast"),
        "fath": state.get("fath"),
        "sota_ready": False,
        "stored_prose": 0,
    })
