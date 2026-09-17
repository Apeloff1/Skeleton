"""Wave-18 play. Brine, pan, rake, crystal."""

from __future__ import annotations

from typing import Any

from skeleton.game.brine_pack import fill
from skeleton.game.crystal_pack import form
from skeleton.game.pan_pack import set_pan
from skeleton.game.rake_pack import pull
from skeleton.game.seal_card import seal
from skeleton.game.wave18_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = fill({"wet": 0, "salt": 0, "crystal": []}, "br_00")
    node = set_pan({"heat": 6}, "pn_00")
    state = pull(state, "rk_00")
    state = form(state, "cr_00")
    info = census()
    return seal({
        "kind": "wave18_play",
        "seed": int(seed),
        "packs": info["n"],
        "brine": state.get("brine"),
        "pan": node.get("pan"),
        "salt": state.get("salt"),
        "crystal": int(bool(state.get("crystal"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
