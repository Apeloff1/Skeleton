"""Second wave-66 pass. Extra bin + weevil."""

from __future__ import annotations

from typing import Any

from skeleton.game.grainbin_pack import fill
from skeleton.game.seal_card import seal
from skeleton.game.weevil_pack import mark


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = fill({"loss": 0}, "gb_01", 4)
    state = mark(state, "wv_01")
    return seal({
        "kind": "wave66_more",
        "seed": int(seed),
        "grain": state.get("grain"),
        "loss": state.get("loss"),
        "sota_ready": False,
        "stored_prose": 0,
    })
