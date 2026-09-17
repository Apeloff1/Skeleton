"""Wave-32 play. Slake, putty, hair, mortar."""

from __future__ import annotations

from typing import Any

from skeleton.game.hair_pack import bind
from skeleton.game.mortar_pack import mix
from skeleton.game.putty_pack import age
from skeleton.game.seal_card import seal
from skeleton.game.slake_pack import slake
from skeleton.game.wave32_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = slake({"wet": 0, "age": 0, "mortar": []}, "sk_00")
    state = age(state, "pt_00")
    state = bind(state, "hr_00")
    state = mix(state, "mt_00")
    info = census()
    return seal({
        "kind": "wave32_play",
        "seed": int(seed),
        "packs": info["n"],
        "slake": state.get("slake"),
        "age": state.get("age"),
        "mortar": int(bool(state.get("mortar"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
