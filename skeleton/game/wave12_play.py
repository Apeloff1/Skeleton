"""Wave-12 play. Graft, prune, harvest, cellar."""

from __future__ import annotations

from typing import Any

from skeleton.game.cellar_pack import stow
from skeleton.game.graft_pack import set_graft
from skeleton.game.harvest_pack import pick
from skeleton.game.prune_pack import cut
from skeleton.game.seal_card import seal
from skeleton.game.wave12_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_graft({"growth": 4}, "gf_00", "stock_a")
    node = cut(node, "pn_00")
    state = pick({"harvest": []}, "hv_00")
    state = stow(state, "cl_00", "hv_00")
    info = census()
    return seal({
        "kind": "wave12_play",
        "seed": int(seed),
        "packs": info["n"],
        "graft": int(bool(node.get("graft"))),
        "harvest": int(bool(state.get("harvest"))),
        "cellar": int(bool(state.get("cellar"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
