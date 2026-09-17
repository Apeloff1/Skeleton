"""Second wave-55 pass. Extra saggar + prop."""

from __future__ import annotations

from typing import Any

from skeleton.game.prop_pack import set_prop
from skeleton.game.saggar_pack import set_saggar
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_saggar({"prop": []}, "sg_01")
    state = set_prop(state, "pr_01")
    return seal({
        "kind": "wave55_more",
        "seed": int(seed),
        "saggar": state.get("saggar"),
        "prop": int(bool(state.get("prop"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
