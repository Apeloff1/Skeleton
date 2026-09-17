"""Second wave-17 pass. Hoop, stave."""

from __future__ import annotations

from typing import Any

from skeleton.game.hoop_pack import set_hoop
from skeleton.game.seal_card import seal
from skeleton.game.stave_pack import set_stave


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_hoop({"hoop": [], "stave": []}, "hp_00")
    state = set_stave(state, "sv_00")
    return seal({
        "kind": "wave17_more",
        "seed": int(seed),
        "hoop": int(bool(state.get("hoop"))),
        "stave": int(bool(state.get("stave"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
