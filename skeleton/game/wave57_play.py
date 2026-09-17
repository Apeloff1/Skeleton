"""Wave-57 play. Tree, pommel, cantle, stirrup."""

from __future__ import annotations

from typing import Any

from skeleton.game.cantle_pack import set_cantle
from skeleton.game.pommel_pack import set_pommel
from skeleton.game.saddletree_pack import set_tree
from skeleton.game.seal_card import seal
from skeleton.game.stirrup_pack import set_stirrup
from skeleton.game.wave57_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_tree({"stirrup": []}, "st_00")
    state = set_pommel(state, "pm_00")
    state = set_cantle(state, "ct_00")
    state = set_stirrup(state, "sr_00")
    info = census()
    return seal({
        "kind": "wave57_play",
        "seed": int(seed),
        "packs": info["n"],
        "saddletree": state.get("saddletree"),
        "pommel": state.get("pommel"),
        "stirrup": int(bool(state.get("stirrup"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
