"""Wave-37 play. Verge, escape, fusee, pendulum."""

from __future__ import annotations

from typing import Any

from skeleton.game.escape_pack import tick
from skeleton.game.fusee_pack import wind
from skeleton.game.pendulum_pack import set_len
from skeleton.game.seal_card import seal
from skeleton.game.verge_pack import set_verge
from skeleton.game.wave37_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_verge({"tick": 0, "wind": 0}, "vg_00")
    state = tick(state, "es_00")
    state = wind(state, "fe_00")
    state = set_len(state, "pd_00", 8)
    info = census()
    return seal({
        "kind": "wave37_play",
        "seed": int(seed),
        "packs": info["n"],
        "escape": state.get("escape"),
        "tick": state.get("tick"),
        "len": state.get("len"),
        "sota_ready": False,
        "stored_prose": 0,
    })
