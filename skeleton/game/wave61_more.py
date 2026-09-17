"""Second wave-61 pass. Extra bow + pin."""

from __future__ import annotations

from typing import Any

from skeleton.game.oxbow_pack import set_bow
from skeleton.game.seal_card import seal
from skeleton.game.yokepin_pack import set_pin


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_bow({"oxbow": []}, "ox_01")
    state = set_pin(state, "yp_01")
    return seal({
        "kind": "wave61_more",
        "seed": int(seed),
        "oxbow": int(bool(state.get("oxbow"))),
        "locked": state.get("locked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
