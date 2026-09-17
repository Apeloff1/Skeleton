"""Wave-97 play. Statute, charter, roll, letters."""

from __future__ import annotations

from typing import Any

from skeleton.game.charter_pack import grant
from skeleton.game.letters_pack import issue
from skeleton.game.roll_pack import enter
from skeleton.game.seal_card import seal
from skeleton.game.statute_pack import enact
from skeleton.game.wave97_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = enact({"roll": []}, "st_00")
    state = grant(state, "ch_00")
    state = enter(state, "rl_00")
    state = issue(state, "lp_00")
    info = census()
    return seal({
        "kind": "wave97_play",
        "seed": int(seed),
        "packs": info["n"],
        "law": state.get("law"),
        "granted": state.get("granted"),
        "issued": state.get("issued"),
        "sota_ready": False,
        "stored_prose": 0,
    })
