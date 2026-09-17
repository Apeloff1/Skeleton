"""Second wave-104 pass. Extra paste + calf."""

from __future__ import annotations

from typing import Any

from skeleton.game.calf_pack import cover as calf_cover
from skeleton.game.paste_pack import glue
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = glue({}, "ps_01")
    state = calf_cover(state, "cf_01")
    return seal({
        "kind": "wave104_more",
        "seed": int(seed),
        "stuck": state.get("stuck"),
        "calf": state.get("calf"),
        "sota_ready": False,
        "stored_prose": 0,
    })
