"""Wave-103 play. Kettle, head, tail, end."""

from __future__ import annotations

from typing import Any

from skeleton.game.endband_pack import set_end
from skeleton.game.headband_pack import set_head
from skeleton.game.kettlestitch_pack import sew
from skeleton.game.seal_card import seal
from skeleton.game.tailband_pack import set_tail
from skeleton.game.wave103_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = sew({"sewn": 0}, "ks_00")
    state = set_head(state, "hb_00")
    state = set_tail(state, "tb_00")
    state = set_end(state, "eb_00")
    info = census()
    return seal({
        "kind": "wave103_play",
        "seed": int(seed),
        "packs": info["n"],
        "sewn": state.get("sewn"),
        "headband": state.get("headband"),
        "endband": state.get("endband"),
        "sota_ready": False,
        "stored_prose": 0,
    })
