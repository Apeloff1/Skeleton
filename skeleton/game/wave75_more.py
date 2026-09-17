"""Second wave-75 pass. Extra wash + cut."""

from __future__ import annotations

from typing import Any

from skeleton.game.foreshot_pack import cut
from skeleton.game.seal_card import seal
from skeleton.game.wash_pack import charge


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = charge({"wet": 0, "cut": 0}, "wa_01")
    state = cut(state, "fs_01")
    return seal({
        "kind": "wave75_more",
        "seed": int(seed),
        "wet": state.get("wet"),
        "cut": state.get("cut"),
        "sota_ready": False,
        "stored_prose": 0,
    })
