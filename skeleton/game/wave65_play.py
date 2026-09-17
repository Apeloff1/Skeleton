"""Wave-65 play. Basket, fan, sieve, chaff."""

from __future__ import annotations

from typing import Any

from skeleton.game.chaff_pack import blow
from skeleton.game.seal_card import seal
from skeleton.game.wave65_index import census
from skeleton.game.winnowbasket_pack import set_basket
from skeleton.game.winnowfan_pack import toss
from skeleton.game.winnowsieve_pack import shake


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_basket({"air": 0, "grain": 0, "light": 0}, "wb_00")
    state = toss(state, "wf_00")
    state = shake(state, "ws_00")
    state = blow(state, "cf_00")
    info = census()
    return seal({
        "kind": "wave65_play",
        "seed": int(seed),
        "packs": info["n"],
        "air": state.get("air"),
        "grain": state.get("grain"),
        "light": state.get("light"),
        "sota_ready": False,
        "stored_prose": 0,
    })
