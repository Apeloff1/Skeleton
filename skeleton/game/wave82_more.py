"""Second wave-82 pass. Extra cut + stack."""

from __future__ import annotations

from typing import Any

from skeleton.game.peatcut_pack import cut
from skeleton.game.peatstack_pack import set_stack
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = cut({"sod": 0, "peatstack": []}, "pc_01")
    state = set_stack(state, "ps_01")
    return seal({
        "kind": "wave82_more",
        "seed": int(seed),
        "sod": state.get("sod"),
        "peatstack": int(bool(state.get("peatstack"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
