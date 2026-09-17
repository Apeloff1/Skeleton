"""Wave-54 play. Ward, bit, bow, tumbler."""

from __future__ import annotations

from typing import Any

from skeleton.game.lockbit_pack import set_bit
from skeleton.game.lockbow_pack import set_bow
from skeleton.game.seal_card import seal
from skeleton.game.tumbler_pack import lift
from skeleton.game.ward_pack import set_ward
from skeleton.game.wave54_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_ward({"ward": [], "lift": 0}, "wd_00")
    state = set_bit(state, "lb_00")
    state = set_bow(state, "lw_00")
    state = lift(state, "tb_00")
    info = census()
    return seal({
        "kind": "wave54_play",
        "seed": int(seed),
        "packs": info["n"],
        "ward": int(bool(state.get("ward"))),
        "lift": state.get("lift"),
        "lockbit": state.get("lockbit"),
        "sota_ready": False,
        "stored_prose": 0,
    })
