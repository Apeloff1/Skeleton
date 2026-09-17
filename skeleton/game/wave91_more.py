"""Second wave-91 pass. Extra assay + hallmark."""

from __future__ import annotations

from typing import Any

from skeleton.game.assay_pack import test
from skeleton.game.hallmark_pack import punch
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = test({}, "as_01")
    state = punch(state, "hm_01")
    return seal({
        "kind": "wave91_more",
        "seed": int(seed),
        "tested": state.get("tested"),
        "marked": state.get("marked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
