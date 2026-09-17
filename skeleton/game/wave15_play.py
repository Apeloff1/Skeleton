"""Wave-15 play. Loom, warp, weft, shuttle."""

from __future__ import annotations

from typing import Any

from skeleton.game.loom_pack import set_loom
from skeleton.game.seal_card import seal
from skeleton.game.shuttle_pack import throw
from skeleton.game.warp_pack import beam
from skeleton.game.wave15_index import census
from skeleton.game.weft_pack import pass_weft


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_loom({}, "lm_00")
    state = beam({"weft": [], "picks": 0}, "wp_00")
    state = pass_weft(state, "wf_00")
    state = throw(state, "sh_00")
    info = census()
    return seal({
        "kind": "wave15_play",
        "seed": int(seed),
        "packs": info["n"],
        "loom": node.get("loom"),
        "warp": state.get("warp"),
        "weft": int(bool(state.get("weft"))),
        "picks": state.get("picks"),
        "sota_ready": False,
        "stored_prose": 0,
    })
