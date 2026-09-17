"""Second wave-23 pass. Extra type + proof."""

from __future__ import annotations

from typing import Any

from skeleton.game.proof_pack import pull
from skeleton.game.seal_card import seal
from skeleton.game.type_pack import set_sort


def play(*, seed: int = 8847291, digest: str = "d") -> dict[str, Any]:
    state = set_sort({"type": {}, "proof": {}}, "ty_01", digest or "d")
    state = pull(state, "pf_01", digest or "d")
    return seal({
        "kind": "wave23_more",
        "seed": int(seed),
        "type": int(bool(state.get("type"))),
        "proof": int(bool(state.get("proof"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
