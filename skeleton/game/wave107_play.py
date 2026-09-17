"""Wave-107 play. Coffer, strap, hasp, casket."""

from __future__ import annotations

from typing import Any

from skeleton.game.casket_pack import set_casket
from skeleton.game.coffer_pack import set_coffer
from skeleton.game.hasp_pack import set_hasp
from skeleton.game.seal_card import seal
from skeleton.game.strap_pack import bind
from skeleton.game.wave107_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_coffer({}, "cf_00")
    state = bind(node, "sp_00")
    state = set_hasp(state, "hp_00")
    state = set_casket(state, "ck_00")
    info = census()
    return seal({
        "kind": "wave107_play",
        "seed": int(seed),
        "packs": info["n"],
        "coffer": state.get("coffer"),
        "tight": state.get("tight"),
        "shut": state.get("shut"),
        "sota_ready": False,
        "stored_prose": 0,
    })
