"""Wave-34 play. Batten, nib, ridge, valley."""

from __future__ import annotations

from typing import Any

from skeleton.game.batten_pack import fix
from skeleton.game.nib_pack import hang
from skeleton.game.ridge_pack import cap
from skeleton.game.seal_card import seal
from skeleton.game.valley_pack import set_valley
from skeleton.game.wave34_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = fix({"batten": [], "tile": 0}, "bt_00")
    node = hang(node, "nb_00")
    node = cap(node, "rg_00")
    node = set_valley(node, "vl_00")
    info = census()
    return seal({
        "kind": "wave34_play",
        "seed": int(seed),
        "packs": info["n"],
        "batten": int(bool(node.get("batten"))),
        "tile": node.get("tile"),
        "ridge": node.get("ridge"),
        "sota_ready": False,
        "stored_prose": 0,
    })
