"""Wave-46 play. Coaming, lid, cleat, scuttle."""

from __future__ import annotations

from typing import Any

from skeleton.game.cleatpin_pack import belay
from skeleton.game.coaming_pack import set_coaming
from skeleton.game.hatchlid_pack import set_lid
from skeleton.game.scuttle_pack import set_scuttle
from skeleton.game.seal_card import seal
from skeleton.game.wave46_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_coaming({}, "cm_00")
    node = set_lid(node, "hl_00", 0)
    state = belay(node, "cl_00")
    state = set_scuttle(state, "sc_00")
    info = census()
    return seal({
        "kind": "wave46_play",
        "seed": int(seed),
        "packs": info["n"],
        "coaming": state.get("coaming"),
        "open": state.get("open"),
        "belay": state.get("belay"),
        "sota_ready": False,
        "stored_prose": 0,
    })
