"""Second wave-72 pass. Extra flitch + gammon."""

from __future__ import annotations

from typing import Any

from skeleton.game.flitch_pack import hang as hang_flitch
from skeleton.game.gammon_pack import hang as hang_gammon
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = hang_flitch({"flitch": [], "gammon": []}, "fl_01")
    state = hang_gammon(state, "gm_01")
    return seal({
        "kind": "wave72_more",
        "seed": int(seed),
        "flitch": int(bool(state.get("flitch"))),
        "gammon": int(bool(state.get("gammon"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
