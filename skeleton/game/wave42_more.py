"""Second wave-42 pass. Extra rib + strake."""

from __future__ import annotations

from typing import Any

from skeleton.game.rib_pack import set_rib
from skeleton.game.seal_card import seal
from skeleton.game.strake_pack import set_strake


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_rib({"rib": [], "strake": []}, "rb_01")
    node = set_strake(node, "sk_01")
    return seal({
        "kind": "wave42_more",
        "seed": int(seed),
        "rib": int(bool(node.get("rib"))),
        "strake": int(bool(node.get("strake"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
