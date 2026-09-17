"""Wave-23 play. Type, galley, chase, proof."""

from __future__ import annotations

from typing import Any

from skeleton.game.chase_pack import lock
from skeleton.game.galley_pack import set_galley
from skeleton.game.proof_pack import pull
from skeleton.game.seal_card import seal
from skeleton.game.type_pack import set_sort
from skeleton.game.wave23_index import census


def play(*, seed: int = 8847291, digest: str = "d") -> dict[str, Any]:
    state = set_sort({"type": {}, "proof": {}}, "ty_00", digest or "d")
    state = set_galley(state, "gy_00")
    state = lock(state, "cs_00")
    state = pull(state, "pf_00", digest or "d")
    info = census()
    return seal({
        "kind": "wave23_play",
        "seed": int(seed),
        "packs": info["n"],
        "type": int(bool(state.get("type"))),
        "locked": state.get("locked"),
        "proof": int(bool(state.get("proof"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
