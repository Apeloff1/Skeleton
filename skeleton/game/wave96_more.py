"""Second wave-96 pass. Extra stone + cwt."""

from __future__ import annotations

from typing import Any

from skeleton.game.hundredweight_pack import weigh as cw_w
from skeleton.game.seal_card import seal
from skeleton.game.stonewt_pack import weigh as st_w


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = st_w({}, "st_01", 1)
    state = cw_w(state, "cw_01", 2)
    return seal({
        "kind": "wave96_more",
        "seed": int(seed),
        "st": state.get("st"),
        "cwt": state.get("cwt"),
        "sota_ready": False,
        "stored_prose": 0,
    })
