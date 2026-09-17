"""Wave-24 play. Coppice, rick, cord, faggot."""

from __future__ import annotations

from typing import Any

from skeleton.game.coppice_pack import cut
from skeleton.game.cord_pack import measure
from skeleton.game.faggot_pack import bind
from skeleton.game.rick_pack import stack
from skeleton.game.seal_card import seal
from skeleton.game.wave24_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = cut({"growth": 4}, "cp_00")
    state = stack({"rick": [], "faggot": [], "wood": 0}, "rk_00")
    state = measure(state, "cd_00")
    state = bind(state, "fg_00")
    info = census()
    return seal({
        "kind": "wave24_play",
        "seed": int(seed),
        "packs": info["n"],
        "coppice": node.get("coppice"),
        "wood": state.get("wood"),
        "faggot": int(bool(state.get("faggot"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
