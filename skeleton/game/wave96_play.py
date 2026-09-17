"""Wave-96 play. Grain, stone, quarter, cwt."""

from __future__ import annotations

from typing import Any

from skeleton.game.grainwt_pack import weigh as gr_w
from skeleton.game.hundredweight_pack import weigh as cw_w
from skeleton.game.quarter_pack import weigh as qr_w
from skeleton.game.seal_card import seal
from skeleton.game.stonewt_pack import weigh as st_w
from skeleton.game.wave96_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = gr_w({}, "gn_00", 480)
    state = st_w(state, "st_00", 2)
    state = qr_w(state, "qr_00", 1)
    state = cw_w(state, "cw_00", 1)
    info = census()
    return seal({
        "kind": "wave96_play",
        "seed": int(seed),
        "packs": info["n"],
        "gr": state.get("gr"),
        "st": state.get("st"),
        "cwt": state.get("cwt"),
        "sota_ready": False,
        "stored_prose": 0,
    })
