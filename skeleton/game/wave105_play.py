"""Wave-105 play. Leaf, burnish, tool, fillet."""

from __future__ import annotations

from typing import Any

from skeleton.game.burnish_pack import rub
from skeleton.game.fillet_pack import roll
from skeleton.game.goldleaf_pack import lay
from skeleton.game.seal_card import seal
from skeleton.game.tooling_pack import stamp
from skeleton.game.wave105_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = lay({}, "gl_00")
    state = rub(state, "bn_00")
    state = stamp(state, "tl_00")
    state = roll(state, "fi_00")
    info = census()
    return seal({
        "kind": "wave105_play",
        "seed": int(seed),
        "packs": info["n"],
        "gilt": state.get("gilt"),
        "shine": state.get("shine"),
        "line": state.get("line"),
        "sota_ready": False,
        "stored_prose": 0,
    })
