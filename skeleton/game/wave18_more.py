"""Second wave-18 pass. Extra rake + crystal."""

from __future__ import annotations

from typing import Any

from skeleton.game.crystal_pack import form
from skeleton.game.rake_pack import pull
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = pull({"salt": 0, "crystal": []}, "rk_01")
    state = form(state, "cr_01")
    return seal({
        "kind": "wave18_more",
        "seed": int(seed),
        "salt": state.get("salt"),
        "crystal": int(bool(state.get("crystal"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
