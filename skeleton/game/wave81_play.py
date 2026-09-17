"""Wave-81 play. Bed, dredge, tongs, rake."""

from __future__ import annotations

from typing import Any

from skeleton.game.dredge_pack import tow
from skeleton.game.oysterrake_pack import rake
from skeleton.game.seal_card import seal
from skeleton.game.shellbed_pack import set_bed
from skeleton.game.tongs_pack import grip
from skeleton.game.wave81_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_bed({"haul": 0, "take": 0}, "sb_00")
    state = tow(node, "dg_00")
    state = grip(state, "tg_00")
    state = rake(state, "or_00")
    info = census()
    return seal({
        "kind": "wave81_play",
        "seed": int(seed),
        "packs": info["n"],
        "shellbed": state.get("shellbed"),
        "haul": state.get("haul"),
        "take": state.get("take"),
        "sota_ready": False,
        "stored_prose": 0,
    })
