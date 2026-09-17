"""Wave-78 play. Brood, queen, super, smoker."""

from __future__ import annotations

from typing import Any

from skeleton.game.brood_pack import set_brood
from skeleton.game.queen_pack import set_queen
from skeleton.game.seal_card import seal
from skeleton.game.smoker_pack import puff
from skeleton.game.supers_pack import add
from skeleton.game.wave78_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_brood({"supers": []}, "bd_00")
    state = set_queen(node, "qn_00")
    state = add(state, "su_00")
    state = puff(state, "sm_00")
    info = census()
    return seal({
        "kind": "wave78_play",
        "seed": int(seed),
        "packs": info["n"],
        "brood": state.get("brood"),
        "queen": state.get("queen"),
        "calm": state.get("calm"),
        "sota_ready": False,
        "stored_prose": 0,
    })
