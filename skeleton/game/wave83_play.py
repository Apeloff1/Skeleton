"""Wave-83 play. Stake, pleach, ether, binder."""

from __future__ import annotations

from typing import Any

from skeleton.game.binder_pack import bind
from skeleton.game.ether_pack import weave
from skeleton.game.hedgestake_pack import drive
from skeleton.game.pleach_pack import lay
from skeleton.game.seal_card import seal
from skeleton.game.wave83_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = drive({"hedgestake": [], "pleach": []}, "hs_00")
    state = lay(state, "pl_00")
    state = weave(state, "et_00")
    state = bind(state, "bd_00")
    info = census()
    return seal({
        "kind": "wave83_play",
        "seed": int(seed),
        "packs": info["n"],
        "hedgestake": int(bool(state.get("hedgestake"))),
        "pleach": int(bool(state.get("pleach"))),
        "tight": state.get("tight"),
        "sota_ready": False,
        "stored_prose": 0,
    })
