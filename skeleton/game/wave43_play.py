"""Wave-43 play. Oakum, seam, iron, pitch."""

from __future__ import annotations

from typing import Any

from skeleton.game.caulkiron_pack import drive
from skeleton.game.oakum_pack import take
from skeleton.game.pitchlot_pack import heat
from skeleton.game.seal_card import seal
from skeleton.game.seam_pack import set_seam
from skeleton.game.wave43_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = take({"oakum": [], "seam": [], "driven": 0, "heat": 6}, "ok_00")
    state = set_seam(state, "sm_00")
    state = drive(state, "ci_00")
    state = heat(state, "ph_00")
    info = census()
    return seal({
        "kind": "wave43_play",
        "seed": int(seed),
        "packs": info["n"],
        "oakum": int(bool(state.get("oakum"))),
        "driven": state.get("driven"),
        "heat": state.get("heat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
