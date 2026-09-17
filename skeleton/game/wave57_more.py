"""Second wave-57 pass. Extra tree + stirrup."""

from __future__ import annotations

from typing import Any

from skeleton.game.saddletree_pack import set_tree
from skeleton.game.seal_card import seal
from skeleton.game.stirrup_pack import set_stirrup


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_tree({"stirrup": []}, "st_01")
    state = set_stirrup(state, "sr_01")
    return seal({
        "kind": "wave57_more",
        "seed": int(seed),
        "saddletree": state.get("saddletree"),
        "stirrup": int(bool(state.get("stirrup"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
