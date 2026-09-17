"""Wave-9 play. Strut, truss, rivet, span, rail."""

from __future__ import annotations

from typing import Any

from skeleton.game.rail_pack import lay
from skeleton.game.rivet_pack import drive
from skeleton.game.seal_card import seal
from skeleton.game.span_pack import set_span
from skeleton.game.strut_pack import set_strut
from skeleton.game.truss_pack import span as truss_span
from skeleton.game.wave9_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_strut({"stress": 0}, "st_00")
    node = truss_span(node, "tr_00", "a", "b")
    node = set_span(node, "sp_00", 8)
    node = lay(node, "rl_00")
    state = drive({"rivet": []}, "rv_00")
    info = census()
    return seal({
        "kind": "wave9_play",
        "seed": int(seed),
        "packs": info["n"],
        "strut": node.get("strut"),
        "span": node.get("length"),
        "rivet": int(bool(state.get("rivet"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
