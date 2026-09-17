"""Wave-30 play. Pulp, deckle, couch, felt."""

from __future__ import annotations

from typing import Any

from skeleton.game.couch_pack import turn
from skeleton.game.deckle_pack import set_deckle
from skeleton.game.felt_pack import press
from skeleton.game.pulp_pack import beat
from skeleton.game.seal_card import seal
from skeleton.game.wave30_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = beat({"wet": 0, "sheet": 0}, "pu_00")
    state = set_deckle(state, "dk_00")
    state = turn(state, "ch_00")
    state = press(state, "ft_00")
    info = census()
    return seal({
        "kind": "wave30_play",
        "seed": int(seed),
        "packs": info["n"],
        "pulp": state.get("pulp"),
        "sheet": state.get("sheet"),
        "wet": state.get("wet"),
        "sota_ready": False,
        "stored_prose": 0,
    })
