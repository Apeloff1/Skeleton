"""Second wave-112 pass. Extra inquisition + livery."""

from __future__ import annotations

from typing import Any

from skeleton.game.inquisition_pack import hold
from skeleton.game.liveryseisin_pack import deliver
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = hold({}, "iq_01")
    state = deliver(state, "lv_01")
    return seal({
        "kind": "wave112_more",
        "seed": int(seed),
        "held": state.get("held"),
        "seised": state.get("seised"),
        "sota_ready": False,
        "stored_prose": 0,
    })
