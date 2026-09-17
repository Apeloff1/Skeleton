"""Wave-25 play. Wattle, daub, lath, thatch."""

from __future__ import annotations

from typing import Any

from skeleton.game.daub_pack import smear
from skeleton.game.lath_pack import nail
from skeleton.game.seal_card import seal
from skeleton.game.thatch_pack import lay
from skeleton.game.wave25_index import census
from skeleton.game.wattle_pack import weave


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = weave({"wet": 0, "lath": [], "thatch": []}, "wt_00")
    node = smear(node, "db_00")
    node = nail(node, "lt_00")
    node = lay(node, "th_00")
    info = census()
    return seal({
        "kind": "wave25_play",
        "seed": int(seed),
        "packs": info["n"],
        "wattle": node.get("wattle"),
        "daub": node.get("daub"),
        "thatch": int(bool(node.get("thatch"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
