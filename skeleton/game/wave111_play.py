"""Wave-111 play. Pipe, close, patent, fine."""

from __future__ import annotations

from typing import Any

from skeleton.game.closeroll_pack import enter as close_enter
from skeleton.game.fineroll_pack import enter as fine_enter
from skeleton.game.patentroll_pack import enter as patent_enter
from skeleton.game.piperoll_pack import enter as pipe_enter
from skeleton.game.seal_card import seal
from skeleton.game.wave111_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = pipe_enter({"owed": 0}, "pr_00")
    state = close_enter(state, "cr_00")
    state = patent_enter(state, "pt_00")
    state = fine_enter(state, "fn_00", 3)
    info = census()
    return seal({
        "kind": "wave111_play",
        "seed": int(seed),
        "packs": info["n"],
        "owed": state.get("owed"),
        "closed": state.get("closed"),
        "fine": state.get("fine"),
        "sota_ready": False,
        "stored_prose": 0,
    })
