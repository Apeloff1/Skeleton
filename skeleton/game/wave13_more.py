"""Second wave-13 pass. Queen, frame, honey."""

from __future__ import annotations

from typing import Any

from skeleton.game.frame_pack import hang
from skeleton.game.honey_pack import jar
from skeleton.game.queen_pack import set_queen
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_queen({}, "qn_00")
    node = hang(node, "fr_00")
    state = jar({"honey": []}, "hn_00")
    return seal({
        "kind": "wave13_more",
        "seed": int(seed),
        "queen": node.get("queen"),
        "frame": int(bool(node.get("frame"))),
        "honey": int(bool(state.get("honey"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
