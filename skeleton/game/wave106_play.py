"""Wave-106 play. Corner, boss, clasp, edge."""

from __future__ import annotations

from typing import Any

from skeleton.game.boss_pack import set_boss
from skeleton.game.clasp_pack import set_clasp
from skeleton.game.cornerpiece_pack import set_corner
from skeleton.game.foredge_pack import paint
from skeleton.game.seal_card import seal
from skeleton.game.wave106_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_corner({"cornerpiece": [], "boss": []}, "cp_00")
    state = set_boss(state, "bs_00")
    state = set_clasp(state, "cl_00")
    state = paint(state, "fe_00")
    info = census()
    return seal({
        "kind": "wave106_play",
        "seed": int(seed),
        "packs": info["n"],
        "shut": state.get("shut"),
        "gilt": state.get("gilt"),
        "boss": int(bool(state.get("boss"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
