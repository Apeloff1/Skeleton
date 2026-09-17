"""Wave-76 play. Trellis, cane, must, lees."""

from __future__ import annotations

from typing import Any

from skeleton.game.cane_pack import prune
from skeleton.game.lees_pack import rack
from skeleton.game.must_pack import press
from skeleton.game.seal_card import seal
from skeleton.game.trellis_pack import set_trellis
from skeleton.game.wave76_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_trellis({"cane": [], "wet": 0}, "tr_00")
    state = prune(node, "cn_00")
    state = press(state, "mu_00")
    state = rack(state, "le_00")
    info = census()
    return seal({
        "kind": "wave76_play",
        "seed": int(seed),
        "packs": info["n"],
        "cane": int(bool(state.get("cane"))),
        "wet": state.get("wet"),
        "clear": state.get("clear"),
        "sota_ready": False,
        "stored_prose": 0,
    })
