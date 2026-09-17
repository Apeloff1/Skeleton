"""Wave-101 play. Quire, prick, rubric, catch."""

from __future__ import annotations

from typing import Any

from skeleton.game.catchword_pack import set_catch
from skeleton.game.pricking_pack import prick
from skeleton.game.quire_pack import fold
from skeleton.game.rubric_pack import mark
from skeleton.game.seal_card import seal
from skeleton.game.wave101_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = fold({}, "qr_00", 8)
    state = prick(state, "pk_00")
    state = mark(state, "rb_00")
    state = set_catch(state, "cw_00")
    info = census()
    return seal({
        "kind": "wave101_play",
        "seed": int(seed),
        "packs": info["n"],
        "leaves": state.get("leaves"),
        "ruled": state.get("ruled"),
        "red": state.get("red"),
        "sota_ready": False,
        "stored_prose": 0,
    })
