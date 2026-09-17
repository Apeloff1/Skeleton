"""Second wave-21 pass. Extra flux + ingot."""

from __future__ import annotations

from typing import Any

from skeleton.game.flux_pack import add
from skeleton.game.ingot_pack import pour
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = add({"flux": [], "ingot": []}, "fx_01")
    state = pour(state, "ig_01")
    return seal({
        "kind": "wave21_more",
        "seed": int(seed),
        "flux": int(bool(state.get("flux"))),
        "ingot": int(bool(state.get("ingot"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
