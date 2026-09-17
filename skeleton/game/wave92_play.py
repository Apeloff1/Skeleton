"""Wave-92 play. Planchet, collar, die, reed."""

from __future__ import annotations

from typing import Any

from skeleton.game.coindie_pack import strike
from skeleton.game.coincollar_pack import set_collar
from skeleton.game.planchet_pack import blank
from skeleton.game.reededge_pack import set_reed
from skeleton.game.seal_card import seal
from skeleton.game.wave92_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = blank({"planchet": [], "struck": 0}, "pl_00")
    state = set_collar(state, "cc_00")
    state = strike(state, "cd_00")
    state = set_reed(state, "re_00")
    info = census()
    return seal({
        "kind": "wave92_play",
        "seed": int(seed),
        "packs": info["n"],
        "planchet": int(bool(state.get("planchet"))),
        "struck": state.get("struck"),
        "reededge": state.get("reededge"),
        "sota_ready": False,
        "stored_prose": 0,
    })
