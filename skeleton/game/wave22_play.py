"""Wave-22 play. Hemp, strand, twist, coil."""

from __future__ import annotations

from typing import Any

from skeleton.game.coil_pack import wind
from skeleton.game.hemp_pack import take
from skeleton.game.seal_card import seal
from skeleton.game.strand_pack import set_strand
from skeleton.game.twist_pack import lay
from skeleton.game.wave22_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = take({"hemp": [], "strand": [], "coil": [], "lay": 0}, "hm_00")
    state = set_strand(state, "st_00")
    state = lay(state, "tw_00")
    state = wind(state, "cl_00")
    info = census()
    return seal({
        "kind": "wave22_play",
        "seed": int(seed),
        "packs": info["n"],
        "hemp": int(bool(state.get("hemp"))),
        "lay": state.get("lay"),
        "coil": int(bool(state.get("coil"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
