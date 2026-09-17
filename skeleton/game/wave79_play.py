"""Wave-79 play. Weir, fyke, line, creel."""

from __future__ import annotations

from typing import Any

from skeleton.game.creel_pack import fill
from skeleton.game.fyke_pack import set_fyke
from skeleton.game.longline_pack import set_line
from skeleton.game.seal_card import seal
from skeleton.game.wave79_index import census
from skeleton.game.weir_pack import set_weir


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_weir({}, "wr_00")
    node = set_fyke(node, "fk_00")
    state = set_line(node, "ll_00", 40)
    state = fill(state, "cr_00", 6)
    info = census()
    return seal({
        "kind": "wave79_play",
        "seed": int(seed),
        "packs": info["n"],
        "weir": state.get("weir"),
        "hooks": state.get("hooks"),
        "catch": state.get("catch"),
        "sota_ready": False,
        "stored_prose": 0,
    })
