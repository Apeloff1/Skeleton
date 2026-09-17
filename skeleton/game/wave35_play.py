"""Wave-35 play. Mortise, tenon, dovetail, rebate."""

from __future__ import annotations

from typing import Any

from skeleton.game.dovetail_pack import cut as dove
from skeleton.game.mortise_pack import cut as mort
from skeleton.game.rebate_pack import plane
from skeleton.game.seal_card import seal
from skeleton.game.tenon_pack import cut as ten
from skeleton.game.wave35_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = mort({"pins": 0}, "mo_00")
    node = ten(node, "tn_00")
    node = dove(node, "dv_00")
    node = plane(node, "rb_00")
    info = census()
    return seal({
        "kind": "wave35_play",
        "seed": int(seed),
        "packs": info["n"],
        "mortise": node.get("mortise"),
        "tenon": node.get("tenon"),
        "pins": node.get("pins"),
        "sota_ready": False,
        "stored_prose": 0,
    })
