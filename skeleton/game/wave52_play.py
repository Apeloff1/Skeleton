"""Wave-52 play. Gnomon, style, hourline, nodus."""

from __future__ import annotations

from typing import Any

from skeleton.game.gnomon_pack import set_gnomon
from skeleton.game.hourline_pack import mark
from skeleton.game.nodus_pack import set_nodus
from skeleton.game.seal_card import seal
from skeleton.game.style_pack import set_style
from skeleton.game.wave52_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_gnomon({"hourline": []}, "gn_00", 6)
    node = set_style(node, "st_00", 52)
    node = mark(node, "hr_00")
    node = set_nodus(node, "nd_00")
    info = census()
    return seal({
        "kind": "wave52_play",
        "seed": int(seed),
        "packs": info["n"],
        "h": node.get("h"),
        "deg": node.get("deg"),
        "hourline": int(bool(node.get("hourline"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
