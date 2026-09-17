"""Wave-6 play. Scent, radio, ration, fuse, trap."""

from __future__ import annotations

from typing import Any

from skeleton.game.fuse_pack import lit, tick as fuse_tick
from skeleton.game.radio_pack import say, tune
from skeleton.game.ration_pack import stamp
from skeleton.game.scent_pack import lay
from skeleton.game.seal_card import seal
from skeleton.game.trap_pack import arm, trip
from skeleton.game.wave6_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = lay({"age": 0}, "sc_00", "player")
    node = arm(node, "tr_00")
    state: dict[str, Any] = {"hp": 40, "heat": 6, "ration": {}, "channel": ""}
    state = tune(state, "ch_00")
    state = say(state, "ch_00", "sc_00")
    state = stamp(state, "rb_00")
    state = lit(state, "fu_00")
    state = fuse_tick(state, "fu_00")
    if node.get("armed"):
        state = trip(state, "tr_00")
    info = census()
    return seal({
        "kind": "wave6_play",
        "seed": int(seed),
        "packs": info["n"],
        "scent": node.get("scent"),
        "heard": state.get("heard"),
        "hp": state.get("hp"),
        "heat": state.get("heat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
