"""Wave-82 play. Bank, slane, cut, stack."""

from __future__ import annotations

from typing import Any

from skeleton.game.peatbank_pack import set_bank
from skeleton.game.peatcut_pack import cut
from skeleton.game.peatstack_pack import set_stack
from skeleton.game.seal_card import seal
from skeleton.game.slane_pack import set_slane
from skeleton.game.wave82_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_bank({"sod": 0, "peatstack": []}, "pb_00")
    state = set_slane(node, "sl_00")
    state = cut(state, "pc_00")
    state = set_stack(state, "ps_00")
    info = census()
    return seal({
        "kind": "wave82_play",
        "seed": int(seed),
        "packs": info["n"],
        "peatbank": state.get("peatbank"),
        "sod": state.get("sod"),
        "peatstack": int(bool(state.get("peatstack"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
