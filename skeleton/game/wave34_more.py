"""Second wave-34 pass. Extra batten + nib."""

from __future__ import annotations

from typing import Any

from skeleton.game.batten_pack import fix
from skeleton.game.nib_pack import hang
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = fix({"batten": [], "tile": 0}, "bt_01")
    node = hang(node, "nb_01")
    return seal({
        "kind": "wave34_more",
        "seed": int(seed),
        "batten": int(bool(node.get("batten"))),
        "tile": node.get("tile"),
        "sota_ready": False,
        "stored_prose": 0,
    })
