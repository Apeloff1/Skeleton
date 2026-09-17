"""Wave-77 play. Root, scion, graft, espalier."""

from __future__ import annotations

from typing import Any

from skeleton.game.espalier_pack import train
from skeleton.game.graft_pack import join
from skeleton.game.rootstock_pack import set_root
from skeleton.game.scion_pack import set_scion
from skeleton.game.seal_card import seal
from skeleton.game.wave77_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_root({}, "rs_00")
    state = set_scion(state, "sc_00")
    state = join(state, "gf_00")
    node = train(state, "es_00")
    info = census()
    return seal({
        "kind": "wave77_play",
        "seed": int(seed),
        "packs": info["n"],
        "rootstock": node.get("rootstock"),
        "take": node.get("take"),
        "espalier": node.get("espalier"),
        "sota_ready": False,
        "stored_prose": 0,
    })
