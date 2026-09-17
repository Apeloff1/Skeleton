"""Second wave-31 pass. Extra pug + batch."""

from __future__ import annotations

from typing import Any

from skeleton.game.batch_pack import set_batch
from skeleton.game.pug_pack import mix
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = mix({"clay": 0, "batch": {}}, "pg_01")
    state = set_batch(state, "bt_01", 4)
    return seal({
        "kind": "wave31_more",
        "seed": int(seed),
        "clay": state.get("clay"),
        "batch": int(bool(state.get("batch"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
