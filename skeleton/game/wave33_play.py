"""Wave-33 play. Scratch, brown, skim, float."""

from __future__ import annotations

from typing import Any

from skeleton.game.brown_pack import lay
from skeleton.game.float_pack import work
from skeleton.game.scratch_pack import key
from skeleton.game.seal_card import seal
from skeleton.game.skim_pack import finish
from skeleton.game.wave33_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = key({"coat": 0}, "sc_00")
    node = lay(node, "br_00")
    node = finish(node, "sm_00")
    node = work(node, "fl_00")
    info = census()
    return seal({
        "kind": "wave33_play",
        "seed": int(seed),
        "packs": info["n"],
        "scratch": node.get("scratch"),
        "skim": node.get("skim"),
        "coat": node.get("coat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
