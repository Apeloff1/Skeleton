"""Wave-51 play. Stone, shoe, damsel, tun."""

from __future__ import annotations

from typing import Any

from skeleton.game.damsel_pack import tap
from skeleton.game.millstone_pack import set_stone
from skeleton.game.seal_card import seal
from skeleton.game.shoe_pack import set_shoe
from skeleton.game.tun_pack import set_tun
from skeleton.game.wave51_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_stone({"tap": 0}, "ms_00")
    node = set_shoe(node, "sh_00", 2)
    state = tap(node, "dm_00")
    state = set_tun(state, "tn_00")
    info = census()
    return seal({
        "kind": "wave51_play",
        "seed": int(seed),
        "packs": info["n"],
        "millstone": state.get("millstone"),
        "feed": state.get("feed"),
        "tap": state.get("tap"),
        "sota_ready": False,
        "stored_prose": 0,
    })
