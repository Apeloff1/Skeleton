"""Second wave-105 pass. Extra leaf + tool."""

from __future__ import annotations

from typing import Any

from skeleton.game.goldleaf_pack import lay
from skeleton.game.seal_card import seal
from skeleton.game.tooling_pack import stamp


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = lay({}, "gl_01")
    state = stamp(state, "tl_01")
    return seal({
        "kind": "wave105_more",
        "seed": int(seed),
        "gilt": state.get("gilt"),
        "stamped": state.get("stamped"),
        "sota_ready": False,
        "stored_prose": 0,
    })
