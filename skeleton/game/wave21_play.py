"""Wave-21 play. Mould, flux, pour, sprue."""

from __future__ import annotations

from typing import Any

from skeleton.game.flux_pack import add
from skeleton.game.ingot_pack import pour
from skeleton.game.mould_pack import set_mould
from skeleton.game.seal_card import seal
from skeleton.game.sprue_pack import cut
from skeleton.game.wave21_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_mould({}, "md_00")
    state = add({"flux": [], "ingot": [], "scrap": 0}, "fx_00")
    state = pour(state, "ig_00")
    state = cut(state, "sp_00")
    info = census()
    return seal({
        "kind": "wave21_play",
        "seed": int(seed),
        "packs": info["n"],
        "mould": node.get("mould"),
        "ingot": int(bool(state.get("ingot"))),
        "scrap": state.get("scrap"),
        "sota_ready": False,
        "stored_prose": 0,
    })
