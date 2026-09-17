"""Wave-98 play. Bench, bar, plea, writ."""

from __future__ import annotations

from typing import Any

from skeleton.game.bar_pack import set_bar
from skeleton.game.courtbench_pack import set_bench
from skeleton.game.plea_pack import enter
from skeleton.game.seal_card import seal
from skeleton.game.wave98_index import census
from skeleton.game.writ_pack import issue


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_bench({}, "cb_00")
    node = set_bar(node, "br_00")
    state = enter(node, "pl_00")
    state = issue(state, "wr_00")
    info = census()
    return seal({
        "kind": "wave98_play",
        "seed": int(seed),
        "packs": info["n"],
        "courtbench": state.get("courtbench"),
        "entered": state.get("entered"),
        "issued": state.get("issued"),
        "sota_ready": False,
        "stored_prose": 0,
    })
