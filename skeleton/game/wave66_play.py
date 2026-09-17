"""Wave-66 play. Crib, loft, bin, weevil."""

from __future__ import annotations

from typing import Any

from skeleton.game.crib_pack import set_crib
from skeleton.game.grainbin_pack import fill
from skeleton.game.hayloft_pack import set_loft
from skeleton.game.seal_card import seal
from skeleton.game.wave66_index import census
from skeleton.game.weevil_pack import mark


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_crib({}, "cb_00")
    node = set_loft(node, "hl_00")
    state = fill(node, "gb_00", 8)
    state = mark(state, "wv_00")
    info = census()
    return seal({
        "kind": "wave66_play",
        "seed": int(seed),
        "packs": info["n"],
        "crib": state.get("crib"),
        "grain": state.get("grain"),
        "loss": state.get("loss"),
        "sota_ready": False,
        "stored_prose": 0,
    })
