"""Second wave-14 pass. Shade, soil."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.shade_pack import draw
from skeleton.game.soil_pack import fill


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = draw({"heat": 8}, "sd_00")
    state = fill({"soil": []}, "so_00")
    return seal({
        "kind": "wave14_more",
        "seed": int(seed),
        "shade": node.get("shade"),
        "heat": node.get("heat"),
        "soil": int(bool(state.get("soil"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
