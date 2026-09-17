"""Second wave-106 pass. Extra clasp + edge."""

from __future__ import annotations

from typing import Any

from skeleton.game.clasp_pack import set_clasp
from skeleton.game.foredge_pack import paint
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_clasp({}, "cl_01")
    state = paint(state, "fe_01")
    return seal({
        "kind": "wave106_more",
        "seed": int(seed),
        "shut": state.get("shut"),
        "gilt": state.get("gilt"),
        "sota_ready": False,
        "stored_prose": 0,
    })
