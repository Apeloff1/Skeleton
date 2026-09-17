"""Wave-53 play. Arming, handlead, mark, deepsea."""

from __future__ import annotations

from typing import Any

from skeleton.game.arming_pack import set_arming
from skeleton.game.deepsea_pack import drop
from skeleton.game.handlead_pack import heave
from skeleton.game.seal_card import seal
from skeleton.game.soundmark_pack import read
from skeleton.game.wave53_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_arming({"cast": 0}, "ar_00")
    state = heave(state, "hd_00")
    state = read(state, "mk_00", 10)
    state = drop(state, "ds_00")
    info = census()
    return seal({
        "kind": "wave53_play",
        "seed": int(seed),
        "packs": info["n"],
        "arming": state.get("arming"),
        "fath": state.get("fath"),
        "cast": state.get("cast"),
        "sota_ready": False,
        "stored_prose": 0,
    })
