"""Wave-68 play. Seedlip, mark, dibble, row."""

from __future__ import annotations

from typing import Any

from skeleton.game.dibble_pack import poke
from skeleton.game.drillrow_pack import sow
from skeleton.game.rowmark_pack import set_mark
from skeleton.game.seal_card import seal
from skeleton.game.seedlip_pack import fill
from skeleton.game.wave68_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = fill({"hole": 0, "drillrow": []}, "sl_00", 8)
    state = set_mark(state, "rm_00")
    state = poke(state, "db_00")
    state = sow(state, "dr_00")
    info = census()
    return seal({
        "kind": "wave68_play",
        "seed": int(seed),
        "packs": info["n"],
        "seed_n": state.get("seed"),
        "hole": state.get("hole"),
        "drillrow": int(bool(state.get("drillrow"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
