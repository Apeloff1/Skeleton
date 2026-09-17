"""Second wave-86 pass. Extra way + cairn."""

from __future__ import annotations

from typing import Any

from skeleton.game.cairn_pack import set_cairn
from skeleton.game.seal_card import seal
from skeleton.game.waymark_pack import set_way


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_way({"waymark": []}, "wm_01")
    node = set_cairn(node, "cn_01")
    return seal({
        "kind": "wave86_more",
        "seed": int(seed),
        "waymark": int(bool(node.get("waymark"))),
        "cairn": node.get("cairn"),
        "sota_ready": False,
        "stored_prose": 0,
    })
