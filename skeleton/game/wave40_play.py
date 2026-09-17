"""Wave-40 play. Boltrope, cringle, grommet, reef."""

from __future__ import annotations

from typing import Any

from skeleton.game.boltrope_pack import sew
from skeleton.game.cringle_pack import set_cringle
from skeleton.game.grommet_pack import set_grommet
from skeleton.game.reef_pack import take
from skeleton.game.seal_card import seal
from skeleton.game.wave40_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = sew({"cringle": [], "grommet": [], "area": 8}, "br_00")
    state = set_cringle(state, "cg_00")
    state = set_grommet(state, "gm_00")
    state = take(state, "rf_00")
    info = census()
    return seal({
        "kind": "wave40_play",
        "seed": int(seed),
        "packs": info["n"],
        "boltrope": state.get("boltrope"),
        "cringle": int(bool(state.get("cringle"))),
        "area": state.get("area"),
        "sota_ready": False,
        "stored_prose": 0,
    })
