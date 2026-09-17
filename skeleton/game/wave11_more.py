"""Second wave-11 pass. Dose, chart, tourniquet."""

from __future__ import annotations

from typing import Any

from skeleton.game.chart_pack import note
from skeleton.game.dose_pack import give
from skeleton.game.seal_card import seal
from skeleton.game.tourniquet_pack import bind


def play(*, seed: int = 8847291, digest: str = "d") -> dict[str, Any]:
    state: dict[str, Any] = {"sleep": 8, "chart": {}, "tq": {}}
    state = give(state, "ds_00")
    state = note(state, "ch_00", digest or "d")
    state = bind(state, "tq_00", "leg_r")
    return seal({
        "kind": "wave11_more",
        "seed": int(seed),
        "dose": state.get("dose"),
        "chart": int(bool(state.get("chart"))),
        "tq": int(bool(state.get("tq"))),
        "sota_ready": False,
        "stored_prose": 0,
    })
