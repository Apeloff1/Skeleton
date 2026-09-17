"""Second wave-108 pass. Extra docket + match."""

from __future__ import annotations

from typing import Any

from skeleton.game.counterpart_pack import match
from skeleton.game.docket_pack import file
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = file({"docket": []}, "dk_01")
    state = match(state, "cp_01")
    return seal({
        "kind": "wave108_more",
        "seed": int(seed),
        "docket": int(bool(state.get("docket"))),
        "fit": state.get("fit"),
        "sota_ready": False,
        "stored_prose": 0,
    })
