"""Wave-84 play. Footing, batter, through, cope."""

from __future__ import annotations

from typing import Any

from skeleton.game.batter_pack import set_batter
from skeleton.game.cope_pack import set_cope
from skeleton.game.footing_pack import set_foot
from skeleton.game.seal_card import seal
from skeleton.game.throughstone_pack import set_thru
from skeleton.game.wave84_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_foot({"throughstone": []}, "ft_00")
    state = set_batter(state, "bt_00", 6)
    state = set_thru(state, "ts_00")
    state = set_cope(state, "cp_00")
    info = census()
    return seal({
        "kind": "wave84_play",
        "seed": int(seed),
        "packs": info["n"],
        "footing": state.get("footing"),
        "slope": state.get("slope"),
        "cope": state.get("cope"),
        "sota_ready": False,
        "stored_prose": 0,
    })
