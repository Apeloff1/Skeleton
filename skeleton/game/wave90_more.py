"""Second wave-90 pass. Extra apprentice + mark."""

from __future__ import annotations

from typing import Any

from skeleton.game.apprentice_pack import bind
from skeleton.game.guildmark_pack import stamp
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = bind({"apprentice": []}, "ap_01")
    state = stamp(state, "gm_01")
    return seal({
        "kind": "wave90_more",
        "seed": int(seed),
        "apprentice": int(bool(state.get("apprentice"))),
        "stamped": state.get("stamped"),
        "sota_ready": False,
        "stored_prose": 0,
    })
