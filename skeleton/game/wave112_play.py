"""Wave-112 play. Inquisition, escheat, ward, livery."""

from __future__ import annotations

from typing import Any

from skeleton.game.escheat_pack import revert
from skeleton.game.inquisition_pack import hold
from skeleton.game.liveryseisin_pack import deliver
from skeleton.game.seal_card import seal
from skeleton.game.wardship_pack import take
from skeleton.game.wave112_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = hold({}, "iq_00")
    state = revert(state, "es_00")
    state = take(state, "wd_00")
    state = deliver(state, "lv_00")
    info = census()
    return seal({
        "kind": "wave112_play",
        "seed": int(seed),
        "packs": info["n"],
        "held": state.get("held"),
        "reverted": state.get("reverted"),
        "seised": state.get("seised"),
        "sota_ready": False,
        "stored_prose": 0,
    })
