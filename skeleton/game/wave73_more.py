"""Second wave-73 pass. Extra wort + hops."""

from __future__ import annotations

from typing import Any

from skeleton.game.hops_pack import add
from skeleton.game.seal_card import seal
from skeleton.game.wort_pack import set_wort


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_wort({"wet": 0, "hops": []}, "wt_01")
    state = add(state, "hp_01")
    return seal({
        "kind": "wave73_more",
        "seed": int(seed),
        "wort": state.get("wort"),
        "hops": int(bool(state.get("hops"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
