"""Second wave-93 pass. Extra poise + pan."""

from __future__ import annotations

from typing import Any

from skeleton.game.poise_pack import slide
from skeleton.game.seal_card import seal
from skeleton.game.weightpan_pack import set_pan


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = slide({}, "po_01", 3)
    state = set_pan(state, "wp_01", 4)
    return seal({
        "kind": "wave93_more",
        "seed": int(seed),
        "arm": state.get("arm"),
        "load": state.get("load"),
        "sota_ready": False,
        "stored_prose": 0,
    })
