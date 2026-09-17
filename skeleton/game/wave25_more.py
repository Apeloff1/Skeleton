"""Second wave-25 pass. Extra lath + thatch."""

from __future__ import annotations

from typing import Any

from skeleton.game.lath_pack import nail
from skeleton.game.seal_card import seal
from skeleton.game.thatch_pack import lay


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = nail({"lath": [], "thatch": []}, "lt_01")
    node = lay(node, "th_01")
    return seal({
        "kind": "wave25_more",
        "seed": int(seed),
        "lath": int(bool(node.get("lath"))),
        "thatch": int(bool(node.get("thatch"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
