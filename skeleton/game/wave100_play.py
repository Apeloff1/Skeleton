"""Wave-100 play. Incipit, terminus, explicit, colophon."""

from __future__ import annotations

from typing import Any

from skeleton.game.colophon_pack import close
from skeleton.game.explicit_pack import end
from skeleton.game.incipit_pack import open_
from skeleton.game.seal_card import seal
from skeleton.game.terminus_pack import bound
from skeleton.game.wave100_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = open_({}, "in_00")
    state = bound(state, "tm_00")
    state = end(state, "ex_00")
    state = close(state, "co_00")
    info = census()
    return seal({
        "kind": "wave100_play",
        "seed": int(seed),
        "packs": info["n"],
        "opened": state.get("opened"),
        "ended": state.get("ended"),
        "closed": state.get("closed"),
        "sota_ready": False,
        "stored_prose": 0,
    })
