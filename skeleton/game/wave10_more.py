"""Second wave-10 pass. Stack, bind, callno, hold."""

from __future__ import annotations

from typing import Any

from skeleton.game.bind_pack import sew
from skeleton.game.callno_pack import assign
from skeleton.game.hold_pack import set_hold
from skeleton.game.seal_card import seal
from skeleton.game.stack_pack import open_stack


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state: dict[str, Any] = {"bind": {}, "callno": {}, "hold": {}}
    state = open_stack(state, "sk_00")
    state = sew(state, "bn_00", "fo_00")
    state = assign(state, "cn_00", "fo_00")
    state = set_hold(state, "hd_00", "player")
    return seal({
        "kind": "wave10_more",
        "seed": int(seed),
        "stack": state.get("stack"),
        "bind": int(bool(state.get("bind"))),
        "callno": int(bool(state.get("callno"))),
        "hold": int(bool(state.get("hold"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
