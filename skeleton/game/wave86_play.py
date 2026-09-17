"""Wave-86 play. Mile, finger, way, cairn."""

from __future__ import annotations

from typing import Any

from skeleton.game.cairn_pack import set_cairn
from skeleton.game.fingerpost_pack import set_finger
from skeleton.game.milestone_pack import set_mile
from skeleton.game.seal_card import seal
from skeleton.game.wave86_index import census
from skeleton.game.waymark_pack import set_way


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_mile({"waymark": []}, "ml_00", 8)
    node = set_finger(node, "fp_00")
    node = set_way(node, "wm_00")
    node = set_cairn(node, "cn_00")
    info = census()
    return seal({
        "kind": "wave86_play",
        "seed": int(seed),
        "packs": info["n"],
        "mi": node.get("mi"),
        "waymark": int(bool(node.get("waymark"))),
        "cairn": node.get("cairn"),
        "sota_ready": False,
        "stored_prose": 0,
    })
