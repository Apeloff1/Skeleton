"""Second wave-80 pass. Extra mesh + sinker."""

from __future__ import annotations

from typing import Any

from skeleton.game.mesh_pack import set_mesh
from skeleton.game.seal_card import seal
from skeleton.game.sinker_pack import set_sink


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_mesh({"sinker": []}, "mh_01", 2)
    state = set_sink(state, "sk_01")
    return seal({
        "kind": "wave80_more",
        "seed": int(seed),
        "size": state.get("size"),
        "sinker": int(bool(state.get("sinker"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
