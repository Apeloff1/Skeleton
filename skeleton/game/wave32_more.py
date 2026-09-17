"""Second wave-32 pass. Extra putty + mortar."""

from __future__ import annotations

from typing import Any

from skeleton.game.mortar_pack import mix
from skeleton.game.putty_pack import age
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = age({"age": 0, "mortar": []}, "pt_01")
    state = mix(state, "mt_01")
    return seal({
        "kind": "wave32_more",
        "seed": int(seed),
        "age": state.get("age"),
        "mortar": int(bool(state.get("mortar"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
