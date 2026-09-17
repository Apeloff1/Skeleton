"""Wave-45 play. Stock, shank, fluke, ring."""

from __future__ import annotations

from typing import Any

from skeleton.game.fluke_pack import set_fluke
from skeleton.game.ringeye_pack import set_ring
from skeleton.game.seal_card import seal
from skeleton.game.shank_pack import set_shank
from skeleton.game.stock_pack import set_stock
from skeleton.game.wave45_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_stock({"hold": 0}, "sk_00")
    state = set_shank(state, "sh_00")
    state = set_fluke(state, "fk_00")
    state = set_ring(state, "re_00")
    info = census()
    return seal({
        "kind": "wave45_play",
        "seed": int(seed),
        "packs": info["n"],
        "stock": state.get("stock"),
        "fluke": state.get("fluke"),
        "hold": state.get("hold"),
        "sota_ready": False,
        "stored_prose": 0,
    })
