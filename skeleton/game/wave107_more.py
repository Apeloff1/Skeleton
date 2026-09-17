"""Second wave-107 pass. Extra hasp + casket."""

from __future__ import annotations

from typing import Any

from skeleton.game.casket_pack import set_casket
from skeleton.game.hasp_pack import set_hasp
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_hasp({}, "hp_01")
    state = set_casket(state, "ck_01")
    return seal({
        "kind": "wave107_more",
        "seed": int(seed),
        "shut": state.get("shut"),
        "casket": state.get("casket"),
        "sota_ready": False,
        "stored_prose": 0,
    })
