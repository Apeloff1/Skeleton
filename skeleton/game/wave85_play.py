"""Wave-85 play. Stile, squeeze, wicket, sneck."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.sneck_pack import latch
from skeleton.game.squeeze_pack import set_squeeze
from skeleton.game.stile_pack import set_stile
from skeleton.game.wave85_index import census
from skeleton.game.wicket_pack import set_wicket


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_stile({}, "st_00")
    node = set_squeeze(node, "sq_00")
    node = set_wicket(node, "wk_00", 0)
    state = latch(node, "sn_00")
    info = census()
    return seal({
        "kind": "wave85_play",
        "seed": int(seed),
        "packs": info["n"],
        "stile": state.get("stile"),
        "open": state.get("open"),
        "latched": state.get("latched"),
        "sota_ready": False,
        "stored_prose": 0,
    })
