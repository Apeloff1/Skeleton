"""Wave-55 play. Saggar, setter, bat, prop."""

from __future__ import annotations

from typing import Any

from skeleton.game.kilnbat_pack import set_bat
from skeleton.game.prop_pack import set_prop
from skeleton.game.saggar_pack import set_saggar
from skeleton.game.seal_card import seal
from skeleton.game.setter_pack import set_setter
from skeleton.game.wave55_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_saggar({"prop": []}, "sg_00")
    state = set_setter(state, "st_00")
    state = set_bat(state, "kb_00")
    state = set_prop(state, "pr_00")
    info = census()
    return seal({
        "kind": "wave55_play",
        "seed": int(seed),
        "packs": info["n"],
        "saggar": state.get("saggar"),
        "kilnbat": state.get("kilnbat"),
        "prop": int(bool(state.get("prop"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
