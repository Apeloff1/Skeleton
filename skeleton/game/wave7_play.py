"""Wave-7 play. Schedule, ticket, locker, punch, ember."""

from __future__ import annotations

from typing import Any

from skeleton.game.ember_pack import drop
from skeleton.game.locker_pack import stow
from skeleton.game.punch_pack import clock_in
from skeleton.game.sched_pack import book
from skeleton.game.seal_card import seal
from skeleton.game.ticket_pack import tear
from skeleton.game.wave7_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state: dict[str, Any] = {"sched": {}, "ticket": [], "locker": {}, "tokens": 8, "heat": 6}
    state = book(state, "sd_00", "player")
    state = tear(state, "tk_00")
    state = stow(state, "lk_00", "scrap", 2)
    state = clock_in(state, "pc_00")
    node = drop({"heat": int(state.get("heat", 0))}, "em_00")
    info = census()
    return seal({
        "kind": "wave7_play",
        "seed": int(seed),
        "packs": info["n"],
        "ticket": int(bool(state.get("ticket"))),
        "tokens": state.get("tokens"),
        "heat": node.get("heat"),
        "sota_ready": False,
        "stored_prose": 0,
    })
