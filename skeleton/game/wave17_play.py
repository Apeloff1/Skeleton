"""Wave-17 play. Hide, vat, lime, bark."""

from __future__ import annotations

from typing import Any

from skeleton.game.bark_pack import tan
from skeleton.game.hide_pack import take
from skeleton.game.lime_pack import add
from skeleton.game.seal_card import seal
from skeleton.game.vat_pack import soak
from skeleton.game.wave17_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = take({"hide": [], "lime": [], "bark": []}, "hd_00")
    node = soak({"soak": 0}, "vt_00")
    state = add(state, "lm_00")
    state = tan(state, "bk_00")
    info = census()
    return seal({
        "kind": "wave17_play",
        "seed": int(seed),
        "packs": info["n"],
        "hide": int(bool(state.get("hide"))),
        "vat": node.get("vat"),
        "lime": int(bool(state.get("lime"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
