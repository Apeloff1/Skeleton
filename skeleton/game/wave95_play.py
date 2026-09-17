"""Wave-95 play. Peck, bushel, gallon, firkin."""

from __future__ import annotations

from typing import Any

from skeleton.game.bushel_pack import fill as bu_fill
from skeleton.game.firkin_pack import fill as fk_fill
from skeleton.game.gallon_pack import fill as gal_fill
from skeleton.game.peck_pack import fill as pk_fill
from skeleton.game.seal_card import seal
from skeleton.game.wave95_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = pk_fill({}, "pk_00", 4)
    state = bu_fill(state, "bu_00", 1)
    state = gal_fill(state, "gl_00", 8)
    state = fk_fill(state, "fk_00", 1)
    info = census()
    return seal({
        "kind": "wave95_play",
        "seed": int(seed),
        "packs": info["n"],
        "pk": state.get("pk"),
        "bu": state.get("bu"),
        "gal": state.get("gal"),
        "sota_ready": False,
        "stored_prose": 0,
    })
