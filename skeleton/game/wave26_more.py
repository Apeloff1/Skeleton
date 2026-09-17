"""Second wave-26 pass. Extra gather + blow."""

from __future__ import annotations

from typing import Any

from skeleton.game.blowpipe_pack import blow
from skeleton.game.gather_pack import dip
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = dip({"heat": 8, "puff": 0}, "gt_01")
    state = blow(state, "bp_01")
    return seal({
        "kind": "wave26_more",
        "seed": int(seed),
        "gather": state.get("gather"),
        "puff": state.get("puff"),
        "sota_ready": False,
        "stored_prose": 0,
    })
