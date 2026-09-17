"""Second wave-68 pass. Extra dibble + row."""

from __future__ import annotations

from typing import Any

from skeleton.game.dibble_pack import poke
from skeleton.game.drillrow_pack import sow
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = poke({"hole": 0, "drillrow": []}, "db_01")
    state = sow(state, "dr_01")
    return seal({
        "kind": "wave68_more",
        "seed": int(seed),
        "hole": state.get("hole"),
        "drillrow": int(bool(state.get("drillrow"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
