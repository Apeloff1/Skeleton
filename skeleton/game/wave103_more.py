"""Second wave-103 pass. Extra kettle + head."""

from __future__ import annotations

from typing import Any

from skeleton.game.headband_pack import set_head
from skeleton.game.kettlestitch_pack import sew
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = sew({"sewn": 0}, "ks_01")
    state = set_head(state, "hb_01")
    return seal({
        "kind": "wave103_more",
        "seed": int(seed),
        "sewn": state.get("sewn"),
        "headband": state.get("headband"),
        "sota_ready": False,
        "stored_prose": 0,
    })
