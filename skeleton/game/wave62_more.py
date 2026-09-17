"""Second wave-62 pass. Extra share + board."""

from __future__ import annotations

from typing import Any

from skeleton.game.mouldboard_pack import set_board
from skeleton.game.ploughshare_pack import set_share
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_share({"turn": 0}, "ps_01")
    state = set_board(state, "mb_01")
    return seal({
        "kind": "wave62_more",
        "seed": int(seed),
        "ploughshare": state.get("ploughshare"),
        "turn": state.get("turn"),
        "sota_ready": False,
        "stored_prose": 0,
    })
