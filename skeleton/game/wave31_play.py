"""Wave-31 play. Pug, frog, clamp, batch."""

from __future__ import annotations

from typing import Any

from skeleton.game.batch_pack import set_batch
from skeleton.game.clamp_pack import fire
from skeleton.game.frog_pack import stamp
from skeleton.game.pug_pack import mix
from skeleton.game.seal_card import seal
from skeleton.game.wave31_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = mix({"clay": 0, "heat": 6, "batch": {}}, "pg_00")
    state = stamp(state, "fr_00")
    state = fire(state, "cm_00")
    state = set_batch(state, "bt_00", 8)
    info = census()
    return seal({
        "kind": "wave31_play",
        "seed": int(seed),
        "packs": info["n"],
        "pug": state.get("pug"),
        "clay": state.get("clay"),
        "batch": int(bool(state.get("batch"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
