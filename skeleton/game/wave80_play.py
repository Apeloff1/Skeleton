"""Wave-80 play. Mesh, selv, cork, sinker."""

from __future__ import annotations

from typing import Any

from skeleton.game.corkline_pack import set_cork
from skeleton.game.mesh_pack import set_mesh
from skeleton.game.seal_card import seal
from skeleton.game.selvedge_pack import set_selv
from skeleton.game.sinker_pack import set_sink
from skeleton.game.wave80_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_mesh({"sinker": []}, "mh_00", 4)
    state = set_selv(state, "sv_00")
    state = set_cork(state, "ck_00")
    state = set_sink(state, "sk_00")
    info = census()
    return seal({
        "kind": "wave80_play",
        "seed": int(seed),
        "packs": info["n"],
        "size": state.get("size"),
        "float": state.get("float"),
        "sinker": int(bool(state.get("sinker"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
