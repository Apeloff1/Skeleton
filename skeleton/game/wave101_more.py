"""Second wave-101 pass. Extra quire + catch."""

from __future__ import annotations

from typing import Any

from skeleton.game.catchword_pack import set_catch
from skeleton.game.quire_pack import fold
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = fold({}, "qr_01", 4)
    state = set_catch(state, "cw_01")
    return seal({
        "kind": "wave101_more",
        "seed": int(seed),
        "leaves": state.get("leaves"),
        "catchword": state.get("catchword"),
        "sota_ready": False,
        "stored_prose": 0,
    })
