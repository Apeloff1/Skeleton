"""Wave-13 play. Hive, comb, swarm, smoke."""

from __future__ import annotations

from typing import Any

from skeleton.game.comb_pack import pull
from skeleton.game.hive_pack import set_hive
from skeleton.game.seal_card import seal
from skeleton.game.smoke_pack import puff
from skeleton.game.swarm_pack import lift
from skeleton.game.wave13_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_hive({"alert": 0}, "hv_00")
    node = lift(node, "sw_00")
    state = puff({"alert": int(node.get("alert", 0)), "comb": []}, "sk_00")
    state = pull(state, "cb_00")
    info = census()
    return seal({
        "kind": "wave13_play",
        "seed": int(seed),
        "packs": info["n"],
        "hive": node.get("hive"),
        "comb": int(bool(state.get("comb"))),
        "alert": state.get("alert"),
        "sota_ready": False,
        "stored_prose": 0,
    })
