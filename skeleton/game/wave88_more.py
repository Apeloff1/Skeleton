"""Second wave-88 pass. Extra tap + settle."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.settle_pack import set_settle
from skeleton.game.taproom_pack import set_tap


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_tap({}, "tp_01")
    node = set_settle(node, "se_01")
    return seal({
        "kind": "wave88_more",
        "seed": int(seed),
        "taproom": node.get("taproom"),
        "settle": node.get("settle"),
        "sota_ready": False,
        "stored_prose": 0,
    })
