"""Second wave-92 pass. Extra blank + strike."""

from __future__ import annotations

from typing import Any

from skeleton.game.coindie_pack import strike
from skeleton.game.planchet_pack import blank
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = blank({"planchet": [], "struck": 0}, "pl_01")
    state = strike(state, "cd_01")
    return seal({
        "kind": "wave92_more",
        "seed": int(seed),
        "planchet": int(bool(state.get("planchet"))),
        "struck": state.get("struck"),
        "sota_ready": False,
        "stored_prose": 0,
    })
