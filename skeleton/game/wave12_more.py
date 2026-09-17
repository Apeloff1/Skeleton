"""Second wave-12 pass. Press, must, cask."""

from __future__ import annotations

from typing import Any

from skeleton.game.cask_pack import fill
from skeleton.game.must_pack import add
from skeleton.game.press_pack import squeeze
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state: dict[str, Any] = {"must": 0, "must_lot": [], "cask": []}
    state = add(state, "mu_00")
    state = squeeze(state, "ps_00")
    state = fill(state, "ck_00")
    return seal({
        "kind": "wave12_more",
        "seed": int(seed),
        "press": state.get("press"),
        "cask": int(bool(state.get("cask"))),
        "must": state.get("must"),
        "sota_ready": False,
        "stored_prose": 0,
    })
