"""Wave-87 play. Ford, step, clapper, pack."""

from __future__ import annotations

from typing import Any

from skeleton.game.clapper_pack import set_clap
from skeleton.game.ford_pack import set_ford
from skeleton.game.packhorse_pack import load
from skeleton.game.seal_card import seal
from skeleton.game.stepstone_pack import set_step
from skeleton.game.wave87_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_ford({"stepstone": []}, "fd_00", 2)
    node = set_step(node, "ss_00")
    node = set_clap(node, "cl_00")
    state = load(node, "ph_00", 4)
    info = census()
    return seal({
        "kind": "wave87_play",
        "seed": int(seed),
        "packs": info["n"],
        "depth": state.get("depth"),
        "clapper": state.get("clapper"),
        "load": state.get("load"),
        "sota_ready": False,
        "stored_prose": 0,
    })
