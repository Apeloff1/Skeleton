"""Wave-26 play. Gather, blowpipe, marver, pontil."""

from __future__ import annotations

from typing import Any

from skeleton.game.blowpipe_pack import blow
from skeleton.game.gather_pack import dip
from skeleton.game.marver_pack import roll
from skeleton.game.pontil_pack import snap
from skeleton.game.seal_card import seal
from skeleton.game.wave26_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = dip({"heat": 8, "puff": 0, "scrap": 0}, "gt_00")
    state = blow(state, "bp_00")
    state = roll(state, "mv_00")
    state = snap(state, "pt_00")
    info = census()
    return seal({
        "kind": "wave26_play",
        "seed": int(seed),
        "packs": info["n"],
        "gather": state.get("gather"),
        "puff": state.get("puff"),
        "scrap": state.get("scrap"),
        "sota_ready": False,
        "stored_prose": 0,
    })
