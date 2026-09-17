"""Second wave-35 pass. Extra mortise + tenon."""

from __future__ import annotations

from typing import Any

from skeleton.game.mortise_pack import cut as mort
from skeleton.game.seal_card import seal
from skeleton.game.tenon_pack import cut as ten


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = mort({}, "mo_01")
    node = ten(node, "tn_01")
    return seal({
        "kind": "wave35_more",
        "seed": int(seed),
        "mortise": node.get("mortise"),
        "tenon": node.get("tenon"),
        "sota_ready": False,
        "stored_prose": 0,
    })
