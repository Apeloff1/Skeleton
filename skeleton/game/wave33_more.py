"""Second wave-33 pass. Extra scratch + skim."""

from __future__ import annotations

from typing import Any

from skeleton.game.scratch_pack import key
from skeleton.game.seal_card import seal
from skeleton.game.skim_pack import finish


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = key({"coat": 0}, "sc_01")
    node = finish(node, "sm_01")
    return seal({
        "kind": "wave33_more",
        "seed": int(seed),
        "scratch": node.get("scratch"),
        "coat": node.get("coat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
