"""Second wave-67 pass. Extra tine + drag."""

from __future__ import annotations

from typing import Any

from skeleton.game.dragbar_pack import drag
from skeleton.game.harrowtine_pack import set_tine
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_tine({"harrowtine": [], "pass": 0}, "ht_01")
    state = drag(state, "db_01")
    return seal({
        "kind": "wave67_more",
        "seed": int(seed),
        "harrowtine": int(bool(state.get("harrowtine"))),
        "pass": state.get("pass"),
        "sota_ready": False,
        "stored_prose": 0,
    })
