"""Second wave-77 pass. Extra scion + graft."""

from __future__ import annotations

from typing import Any

from skeleton.game.graft_pack import join
from skeleton.game.scion_pack import set_scion
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_scion({}, "sc_01")
    state = join(state, "gf_01")
    return seal({
        "kind": "wave77_more",
        "seed": int(seed),
        "scion": state.get("scion"),
        "take": state.get("take"),
        "sota_ready": False,
        "stored_prose": 0,
    })
