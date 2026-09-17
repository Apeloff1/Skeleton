"""Second wave-111 pass. Extra pipe + fine."""

from __future__ import annotations

from typing import Any

from skeleton.game.fineroll_pack import enter as fine_enter
from skeleton.game.piperoll_pack import enter as pipe_enter
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = pipe_enter({"owed": 0}, "pr_01")
    state = fine_enter(state, "fn_01", 1)
    return seal({
        "kind": "wave111_more",
        "seed": int(seed),
        "owed": state.get("owed"),
        "fine": state.get("fine"),
        "sota_ready": False,
        "stored_prose": 0,
    })
