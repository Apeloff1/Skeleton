"""Wave-99 play. Poll, hide, tithe, geld."""

from __future__ import annotations

from typing import Any

from skeleton.game.geld_pack import levy as geld_levy
from skeleton.game.hideacre_pack import set_hide
from skeleton.game.poll_pack import count
from skeleton.game.seal_card import seal
from skeleton.game.tithe_pack import levy as tithe_levy
from skeleton.game.wave99_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = count({}, "po_00", 40)
    state = set_hide(state, "hd_00", 5)
    state = tithe_levy(state, "ti_00", 4)
    state = geld_levy(state, "gd_00", 2)
    info = census()
    return seal({
        "kind": "wave99_play",
        "seed": int(seed),
        "packs": info["n"],
        "heads": state.get("heads"),
        "hide": state.get("hide"),
        "due": state.get("due"),
        "sota_ready": False,
        "stored_prose": 0,
    })
