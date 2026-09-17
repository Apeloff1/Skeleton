"""Wave-42 play. Keel, rib, garboard, strake."""

from __future__ import annotations

from typing import Any

from skeleton.game.garboard_pack import set_garboard
from skeleton.game.keel_pack import set_keel
from skeleton.game.rib_pack import set_rib
from skeleton.game.seal_card import seal
from skeleton.game.strake_pack import set_strake
from skeleton.game.wave42_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_keel({"rib": [], "strake": []}, "kl_00")
    node = set_rib(node, "rb_00")
    node = set_garboard(node, "gb_00")
    node = set_strake(node, "sk_00")
    info = census()
    return seal({
        "kind": "wave42_play",
        "seed": int(seed),
        "packs": info["n"],
        "keel": node.get("keel"),
        "rib": int(bool(node.get("rib"))),
        "strake": int(bool(node.get("strake"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
