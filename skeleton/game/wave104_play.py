"""Wave-104 play. Board, paste, calf, morocco."""

from __future__ import annotations

from typing import Any

from skeleton.game.boardcover_pack import set_board
from skeleton.game.calf_pack import cover as calf_cover
from skeleton.game.morocco_pack import cover as mor_cover
from skeleton.game.paste_pack import glue
from skeleton.game.seal_card import seal
from skeleton.game.wave104_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_board({}, "bc_00")
    state = glue(state, "ps_00")
    state = calf_cover(state, "cf_00")
    state = mor_cover(state, "mo_00")
    info = census()
    return seal({
        "kind": "wave104_play",
        "seed": int(seed),
        "packs": info["n"],
        "boardcover": state.get("boardcover"),
        "stuck": state.get("stuck"),
        "morocco": state.get("morocco"),
        "sota_ready": False,
        "stored_prose": 0,
    })
