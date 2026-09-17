"""Wave-39 play. Sextant, logchip, leadline, azimuth."""

from __future__ import annotations

from typing import Any

from skeleton.game.azimuth_pack import set_az
from skeleton.game.leadline_pack import cast
from skeleton.game.logchip_pack import heave
from skeleton.game.seal_card import seal
from skeleton.game.sextant_pack import shoot
from skeleton.game.wave39_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = shoot({}, "sx_00", 32)
    state = heave(state, "lg_00", 6)
    state = cast(state, "ld_00", 12)
    state = set_az(state, "az_00", 45)
    info = census()
    return seal({
        "kind": "wave39_play",
        "seed": int(seed),
        "packs": info["n"],
        "alt": state.get("alt"),
        "kn": state.get("kn"),
        "deg": state.get("deg"),
        "sota_ready": False,
        "stored_prose": 0,
    })
