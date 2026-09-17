"""Second wave-58 pass. Extra hame + trace."""

from __future__ import annotations

from typing import Any

from skeleton.game.hame_pack import set_hame
from skeleton.game.seal_card import seal
from skeleton.game.traceset_pack import set_trace


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_hame({"hame": [], "trace": []}, "hm_01")
    state = set_trace(state, "tr_01")
    return seal({
        "kind": "wave58_more",
        "seed": int(seed),
        "hame": int(bool(state.get("hame"))),
        "trace": int(bool(state.get("trace"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
