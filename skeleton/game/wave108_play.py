"""Wave-108 play. Box, docket, indenture, counterpart."""

from __future__ import annotations

from typing import Any

from skeleton.game.counterpart_pack import match
from skeleton.game.deedbox_pack import set_box
from skeleton.game.docket_pack import file
from skeleton.game.indenture_pack import cut
from skeleton.game.seal_card import seal
from skeleton.game.wave108_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_box({"docket": []}, "dx_00")
    state = file(node, "dk_00")
    state = cut(state, "id_00")
    state = match(state, "cp_00")
    info = census()
    return seal({
        "kind": "wave108_play",
        "seed": int(seed),
        "packs": info["n"],
        "docket": int(bool(state.get("docket"))),
        "cut": state.get("cut"),
        "fit": state.get("fit"),
        "sota_ready": False,
        "stored_prose": 0,
    })
