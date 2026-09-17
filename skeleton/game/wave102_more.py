"""Second wave-102 pass. Extra gall + quill."""

from __future__ import annotations

from typing import Any

from skeleton.game.oakgall_pack import crush
from skeleton.game.quillcut_pack import cut
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = crush({"ink": 0}, "og_01")
    state = cut(state, "qc_01")
    return seal({
        "kind": "wave102_more",
        "seed": int(seed),
        "ink": state.get("ink"),
        "nib": state.get("nib"),
        "sota_ready": False,
        "stored_prose": 0,
    })
