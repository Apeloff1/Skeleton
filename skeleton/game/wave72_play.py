"""Wave-72 play. House, cure, flitch, gammon."""

from __future__ import annotations

from typing import Any

from skeleton.game.cure_pack import set_cure
from skeleton.game.flitch_pack import hang as hang_flitch
from skeleton.game.gammon_pack import hang as hang_gammon
from skeleton.game.seal_card import seal
from skeleton.game.smokehouse_pack import set_house
from skeleton.game.wave72_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_house({"heat": 4, "days": 0, "flitch": [], "gammon": []}, "sh_00")
    state = set_cure(node, "cu_00")
    state = hang_flitch(state, "fl_00")
    state = hang_gammon(state, "gm_00")
    info = census()
    return seal({
        "kind": "wave72_play",
        "seed": int(seed),
        "packs": info["n"],
        "days": state.get("days"),
        "flitch": int(bool(state.get("flitch"))),
        "gammon": int(bool(state.get("gammon"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
