"""Second wave-65 pass. Extra fan + sieve."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.winnowfan_pack import toss
from skeleton.game.winnowsieve_pack import shake


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = toss({"air": 0, "grain": 0}, "wf_01")
    state = shake(state, "ws_01")
    return seal({
        "kind": "wave65_more",
        "seed": int(seed),
        "air": state.get("air"),
        "grain": state.get("grain"),
        "sota_ready": False,
        "stored_prose": 0,
    })
