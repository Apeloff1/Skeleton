"""Wave-89 play. Pitch, stall, fee, cryer."""

from __future__ import annotations

from typing import Any

from skeleton.game.cryer_pack import cry
from skeleton.game.marketstall_pack import set_stall
from skeleton.game.pitch_pack import set_pitch
from skeleton.game.seal_card import seal
from skeleton.game.stallage_pack import levy
from skeleton.game.wave89_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_pitch({}, "pi_00")
    node = set_stall(node, "ms_00")
    state = levy(node, "sf_00", 2)
    state = cry(state, "cy_00")
    info = census()
    return seal({
        "kind": "wave89_play",
        "seed": int(seed),
        "packs": info["n"],
        "pitch": state.get("pitch"),
        "fee": state.get("fee"),
        "heard": state.get("heard"),
        "sota_ready": False,
        "stored_prose": 0,
    })
