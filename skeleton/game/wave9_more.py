"""Second wave-9 pass. Switch, signal, bolt, survey, wind."""

from __future__ import annotations

from typing import Any

from skeleton.game.bolt_pack import drive
from skeleton.game.seal_card import seal
from skeleton.game.signal_pack import set_aspect
from skeleton.game.survey_pack import log
from skeleton.game.switch_pack import throw
from skeleton.game.wind_pack import set_wind


def play(*, seed: int = 8847291, digest: str = "d") -> dict[str, Any]:
    node = throw({}, "sw_00", 1)
    node = set_aspect(node, "sg_00", 1)
    node = set_wind(node, "wn_00", 4)
    state = drive({"bolt": []}, "bt_00")
    state = log(state, "sy_00", digest or "d")
    return seal({
        "kind": "wave9_more",
        "seed": int(seed),
        "switch": node.get("switch"),
        "aspect": node.get("aspect"),
        "bolt": int(bool(state.get("bolt"))),
        "survey": int(bool(state.get("survey"))),
        "wind": node.get("force"),
        "sota_ready": False,
        "stored_prose": 0,
    })
