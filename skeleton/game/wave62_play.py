"""Wave-62 play. Beam, coulter, share, board."""

from __future__ import annotations

from typing import Any

from skeleton.game.coulter_pack import set_coulter
from skeleton.game.mouldboard_pack import set_board
from skeleton.game.ploughbeam_pack import set_beam
from skeleton.game.ploughshare_pack import set_share
from skeleton.game.seal_card import seal
from skeleton.game.wave62_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_beam({"turn": 0}, "pb_00")
    state = set_coulter(state, "ct_00")
    state = set_share(state, "ps_00")
    state = set_board(state, "mb_00")
    info = census()
    return seal({
        "kind": "wave62_play",
        "seed": int(seed),
        "packs": info["n"],
        "ploughbeam": state.get("ploughbeam"),
        "ploughshare": state.get("ploughshare"),
        "turn": state.get("turn"),
        "sota_ready": False,
        "stored_prose": 0,
    })
