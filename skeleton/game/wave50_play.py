"""Wave-50 play. Adze, croze, chime, bung."""

from __future__ import annotations

from typing import Any

from skeleton.game.adze_pack import hew
from skeleton.game.bung_pack import set_bung
from skeleton.game.chime_pack import set_chime
from skeleton.game.croze_pack import cut
from skeleton.game.seal_card import seal
from skeleton.game.wave50_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = hew({"hewn": 0}, "az_00")
    state = cut(state, "cz_00")
    state = set_chime(state, "cm_00")
    state = set_bung(state, "bg_00")
    info = census()
    return seal({
        "kind": "wave50_play",
        "seed": int(seed),
        "packs": info["n"],
        "hewn": state.get("hewn"),
        "groove": state.get("groove"),
        "sealed": state.get("sealed"),
        "sota_ready": False,
        "stored_prose": 0,
    })
