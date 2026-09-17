"""Wave-67 play. Frame, tine, hitch, drag."""

from __future__ import annotations

from typing import Any

from skeleton.game.dragbar_pack import drag
from skeleton.game.drawhit_pack import hitch
from skeleton.game.harrowframe_pack import set_frame
from skeleton.game.harrowtine_pack import set_tine
from skeleton.game.seal_card import seal
from skeleton.game.wave67_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_frame({"harrowtine": [], "pass": 0}, "hf_00")
    state = set_tine(state, "ht_00")
    state = hitch(state, "dh_00")
    state = drag(state, "db_00")
    info = census()
    return seal({
        "kind": "wave67_play",
        "seed": int(seed),
        "packs": info["n"],
        "harrowframe": state.get("harrowframe"),
        "hitched": state.get("hitched"),
        "pass": state.get("pass"),
        "sota_ready": False,
        "stored_prose": 0,
    })
