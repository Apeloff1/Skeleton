"""Wave-88 play. Sign, tap, cellar, settle."""

from __future__ import annotations

from typing import Any

from skeleton.game.cellar_pack import set_cellar
from skeleton.game.innsign_pack import hang
from skeleton.game.seal_card import seal
from skeleton.game.settle_pack import set_settle
from skeleton.game.taproom_pack import set_tap
from skeleton.game.wave88_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = hang({}, "is_00")
    node = set_tap(node, "tp_00")
    node = set_cellar(node, "cl_00", 4)
    node = set_settle(node, "se_00")
    info = census()
    return seal({
        "kind": "wave88_play",
        "seed": int(seed),
        "packs": info["n"],
        "innsign": node.get("innsign"),
        "cool": node.get("cool"),
        "settle": node.get("settle"),
        "sota_ready": False,
        "stored_prose": 0,
    })
