"""Wave-11 play. Splint, suture, poultice, tonic."""

from __future__ import annotations

from typing import Any

from skeleton.game.poultice_pack import apply
from skeleton.game.seal_card import seal
from skeleton.game.splint_pack import set_splint
from skeleton.game.suture_pack import close
from skeleton.game.tonic_pack import drink
from skeleton.game.wave11_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state: dict[str, Any] = {"hp": 30, "sleep": 8, "splint": {}, "suture": {}}
    state = set_splint(state, "sp_00", "arm_l")
    state = close(state, "su_00", "arm_l")
    state = apply(state, "po_00")
    state = drink(state, "to_00")
    info = census()
    return seal({
        "kind": "wave11_play",
        "seed": int(seed),
        "packs": info["n"],
        "hp": state.get("hp"),
        "sleep": state.get("sleep"),
        "splint": int(bool(state.get("splint"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
