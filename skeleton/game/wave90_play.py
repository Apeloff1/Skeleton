"""Wave-90 play. Hall, apprentice, journey, mark."""

from __future__ import annotations

from typing import Any

from skeleton.game.apprentice_pack import bind
from skeleton.game.guildhall_pack import set_hall
from skeleton.game.guildmark_pack import stamp
from skeleton.game.journeyman_pack import set_journey
from skeleton.game.seal_card import seal
from skeleton.game.wave90_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_hall({"apprentice": []}, "gh_00")
    state = bind(node, "ap_00")
    state = set_journey(state, "jy_00")
    state = stamp(state, "gm_00")
    info = census()
    return seal({
        "kind": "wave90_play",
        "seed": int(seed),
        "packs": info["n"],
        "guildhall": state.get("guildhall"),
        "apprentice": int(bool(state.get("apprentice"))),
        "stamped": state.get("stamped"),
        "sota_ready": False,
        "stored_prose": 0,
    })
