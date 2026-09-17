"""Second wave-95 pass. Extra peck + gallon."""

from __future__ import annotations

from typing import Any

from skeleton.game.gallon_pack import fill as gal_fill
from skeleton.game.peck_pack import fill as pk_fill
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = pk_fill({}, "pk_01", 2)
    state = gal_fill(state, "gl_01", 4)
    return seal({
        "kind": "wave95_more",
        "seed": int(seed),
        "pk": state.get("pk"),
        "gal": state.get("gal"),
        "sota_ready": False,
        "stored_prose": 0,
    })
