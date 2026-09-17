"""Second wave-85 pass. Extra wicket + sneck."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.sneck_pack import latch
from skeleton.game.wicket_pack import set_wicket


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_wicket({}, "wk_01", 1)
    state = latch(node, "sn_01")
    return seal({
        "kind": "wave85_more",
        "seed": int(seed),
        "open": state.get("open"),
        "latched": state.get("latched"),
        "sota_ready": False,
        "stored_prose": 0,
    })
