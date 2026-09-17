"""Second wave-16 pass. Weir, channel."""

from __future__ import annotations

from typing import Any

from skeleton.game.channel_pack import cut
from skeleton.game.seal_card import seal
from skeleton.game.weir_pack import set_weir


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_weir({}, "wr_00", 6)
    node = cut(node, "ch_00", "cs_00")
    return seal({
        "kind": "wave16_more",
        "seed": int(seed),
        "weir": node.get("weir"),
        "level": node.get("level"),
        "channel": node.get("channel"),
        "sota_ready": False,
        "stored_prose": 0,
    })
