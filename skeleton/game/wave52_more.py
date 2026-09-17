"""Second wave-52 pass. Extra hourline + nodus."""

from __future__ import annotations

from typing import Any

from skeleton.game.hourline_pack import mark
from skeleton.game.nodus_pack import set_nodus
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = mark({"hourline": []}, "hr_01")
    node = set_nodus(node, "nd_01")
    return seal({
        "kind": "wave52_more",
        "seed": int(seed),
        "hourline": int(bool(node.get("hourline"))),
        "nodus": node.get("nodus"),
        "sota_ready": False,
        "stored_prose": 0,
    })
