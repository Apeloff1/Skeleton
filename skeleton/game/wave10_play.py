"""Wave-10 play. Folio, shelf, slip, loan."""

from __future__ import annotations

from typing import Any

from skeleton.game.folio_pack import open_folio
from skeleton.game.loan_pack import out
from skeleton.game.seal_card import seal
from skeleton.game.shelf_pack import put
from skeleton.game.slip_pack import write
from skeleton.game.wave10_index import census


def play(*, seed: int = 8847291, digest: str = "d") -> dict[str, Any]:
    state: dict[str, Any] = {"folio": {}, "shelf": {}, "slip": {}, "loan": {}}
    state = open_folio(state, "fo_00", digest or "d")
    state = put(state, "sh_00", "fo_00")
    state = write(state, "sp_00", "fo_00")
    state = out(state, "ln_00", "player")
    info = census()
    return seal({
        "kind": "wave10_play",
        "seed": int(seed),
        "packs": info["n"],
        "folio": int(bool(state.get("folio"))),
        "shelf": int(bool(state.get("shelf"))),
        "loan": int(bool(state.get("loan"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
