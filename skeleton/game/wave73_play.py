"""Wave-73 play. Mash, sparge, wort, hops."""

from __future__ import annotations

from typing import Any

from skeleton.game.hops_pack import add
from skeleton.game.mash_pack import set_mash
from skeleton.game.seal_card import seal
from skeleton.game.sparge_pack import rinse
from skeleton.game.wave73_index import census
from skeleton.game.wort_pack import set_wort


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_mash({"heat": 8, "wet": 0, "hops": []}, "ms_00")
    state = rinse(state, "sg_00")
    state = set_wort(state, "wt_00")
    state = add(state, "hp_00")
    info = census()
    return seal({
        "kind": "wave73_play",
        "seed": int(seed),
        "packs": info["n"],
        "mash": state.get("mash"),
        "wet": state.get("wet"),
        "hops": int(bool(state.get("hops"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
