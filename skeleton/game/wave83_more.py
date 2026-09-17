"""Second wave-83 pass. Extra pleach + bind."""

from __future__ import annotations

from typing import Any

from skeleton.game.binder_pack import bind
from skeleton.game.pleach_pack import lay
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = lay({"pleach": []}, "pl_01")
    state = bind(state, "bd_01")
    return seal({
        "kind": "wave83_more",
        "seed": int(seed),
        "pleach": int(bool(state.get("pleach"))),
        "tight": state.get("tight"),
        "sota_ready": False,
        "stored_prose": 0,
    })
