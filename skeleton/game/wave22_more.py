"""Second wave-22 pass. Extra strand + coil."""

from __future__ import annotations

from typing import Any

from skeleton.game.coil_pack import wind
from skeleton.game.seal_card import seal
from skeleton.game.strand_pack import set_strand


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_strand({"strand": [], "coil": []}, "st_01")
    state = wind(state, "cl_01")
    return seal({
        "kind": "wave22_more",
        "seed": int(seed),
        "strand": int(bool(state.get("strand"))),
        "coil": int(bool(state.get("coil"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
