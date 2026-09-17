"""Wave-58 play. Collar, hame, trace, breeching."""

from __future__ import annotations

from typing import Any

from skeleton.game.breeching_pack import set_breech
from skeleton.game.hame_pack import set_hame
from skeleton.game.horsecollar_pack import set_collar
from skeleton.game.seal_card import seal
from skeleton.game.traceset_pack import set_trace
from skeleton.game.wave58_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_collar({"hame": [], "trace": []}, "hc_00")
    state = set_hame(state, "hm_00")
    state = set_trace(state, "tr_00")
    state = set_breech(state, "br_00")
    info = census()
    return seal({
        "kind": "wave58_play",
        "seed": int(seed),
        "packs": info["n"],
        "horsecollar": state.get("horsecollar"),
        "hame": int(bool(state.get("hame"))),
        "breeching": state.get("breeching"),
        "sota_ready": False,
        "stored_prose": 0,
    })
