"""Wave-61 play. Beam, bow, staple, pin."""

from __future__ import annotations

from typing import Any

from skeleton.game.oxbow_pack import set_bow
from skeleton.game.seal_card import seal
from skeleton.game.wave61_index import census
from skeleton.game.yokebeam_pack import set_beam
from skeleton.game.yokepin_pack import set_pin
from skeleton.game.yokestaple_pack import set_staple


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = set_beam({"oxbow": []}, "yb_00")
    state = set_bow(state, "ox_00")
    state = set_staple(state, "ys_00")
    state = set_pin(state, "yp_00")
    info = census()
    return seal({
        "kind": "wave61_play",
        "seed": int(seed),
        "packs": info["n"],
        "yokebeam": state.get("yokebeam"),
        "oxbow": int(bool(state.get("oxbow"))),
        "locked": state.get("locked"),
        "sota_ready": False,
        "stored_prose": 0,
    })
