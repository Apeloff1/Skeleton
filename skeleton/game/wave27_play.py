"""Wave-27 play. Mordant, bath, indigo, madder."""

from __future__ import annotations

from typing import Any

from skeleton.game.bath_pack import set_bath
from skeleton.game.indigo_pack import dip
from skeleton.game.madder_pack import steep
from skeleton.game.mordant_pack import set_mordant
from skeleton.game.seal_card import seal
from skeleton.game.wave27_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_mordant({"wet": 0, "heat": 6}, "md_00")
    state = set_bath(state, "bh_00")
    state = dip(state, "in_00")
    state = steep(state, "mr_00")
    info = census()
    return seal({
        "kind": "wave27_play",
        "seed": int(seed),
        "packs": info["n"],
        "mordant": state.get("mordant"),
        "bath": state.get("bath"),
        "wet": state.get("wet"),
        "sota_ready": False,
        "stored_prose": 0,
    })
