"""Wave-63 play. Snath, tang, heel, beard."""

from __future__ import annotations

from typing import Any

from skeleton.game.beard_pack import set_beard
from skeleton.game.scytheheel_pack import set_heel
from skeleton.game.seal_card import seal
from skeleton.game.snath_pack import set_snath
from skeleton.game.tang_pack import set_tang
from skeleton.game.wave63_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_snath({"cut": 0}, "sn_00")
    state = set_tang(state, "tg_00")
    state = set_heel(state, "hl_00")
    state = set_beard(state, "bd_00")
    info = census()
    return seal({
        "kind": "wave63_play",
        "seed": int(seed),
        "packs": info["n"],
        "snath": state.get("snath"),
        "tang": state.get("tang"),
        "cut": state.get("cut"),
        "sota_ready": False,
        "stored_prose": 0,
    })
