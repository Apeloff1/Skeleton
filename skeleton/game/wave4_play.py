"""Wave-4 play. Weather + lock + heat + extract once."""

from __future__ import annotations

from typing import Any

from skeleton.game.floors import weave_campus
from skeleton.game.seal_card import seal
from skeleton.game.wave4_index import census
from skeleton.game.wave4_tables import heat_emit, lock_open, weather_tick


class Wave4PlayError(ValueError):
    pass


def play(*, seed: int = 8847291) -> dict[str, Any]:
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    nodes = [weather_tick("wx_00", dict(n), 3) for n in campus["nodes"]]
    nodes = [heat_emit("src_00", n) for n in nodes]
    state = {"key": 3, "heat": max(int(n.get("heat", 0)) for n in nodes), "extracted": 0}
    try:
        state = lock_open("lock_00", state)
        opened = 1
    except Exception:
        opened = 0
    if int(state.get("heat", 0)) >= 8 and int(state.get("extracted", 0)) == 0:
        state["extracted"] = 1
        state["warp_count"] = 1
    info = census()
    return seal({
        "kind": "wave4_play",
        "seed": int(seed),
        "packs": info["n"],
        "opened": opened,
        "peak": state["heat"],
        "extract_count": int(state.get("extracted", 0)),
        "warp_count": int(state.get("warp_count", 0)),
        "sota_ready": False,
        "stored_prose": 0,
    })
