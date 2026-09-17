"""Second wave-100 pass. Extra explicit + colophon."""

from __future__ import annotations

from typing import Any

from skeleton.game.colophon_pack import close
from skeleton.game.explicit_pack import end
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = end({}, "ex_01")
    state = close(state, "co_01")
    return seal({
        "kind": "wave100_more",
        "seed": int(seed),
        "ended": state.get("ended"),
        "closed": state.get("closed"),
        "sota_ready": False,
        "stored_prose": 0,
    })
