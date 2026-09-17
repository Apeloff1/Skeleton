"""Wave-102 play. Gall, black, quill, pounce."""

from __future__ import annotations

from typing import Any

from skeleton.game.lampblack_pack import mix
from skeleton.game.oakgall_pack import crush
from skeleton.game.pounce_pack import dust
from skeleton.game.quillcut_pack import cut
from skeleton.game.seal_card import seal
from skeleton.game.wave102_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = crush({"ink": 0}, "og_00")
    state = mix(state, "lb_00")
    state = cut(state, "qc_00")
    state = dust(state, "pn_00")
    info = census()
    return seal({
        "kind": "wave102_play",
        "seed": int(seed),
        "packs": info["n"],
        "ink": state.get("ink"),
        "nib": state.get("nib"),
        "dry": state.get("dry"),
        "sota_ready": False,
        "stored_prose": 0,
    })
