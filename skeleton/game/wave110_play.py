"""Wave-110 play. Registry, enrol, calendar, memorial."""

from __future__ import annotations

from typing import Any

from skeleton.game.calendaroll_pack import enter
from skeleton.game.enrolment_pack import enrol
from skeleton.game.memorial_pack import record
from skeleton.game.registry_pack import set_reg
from skeleton.game.seal_card import seal
from skeleton.game.wave110_index import census


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = set_reg({"enrolment": []}, "rg_00")
    state = enrol(node, "en_00")
    state = enter(state, "cr_00")
    state = record(state, "mm_00")
    info = census()
    return seal({
        "kind": "wave110_play",
        "seed": int(seed),
        "packs": info["n"],
        "enrolment": int(bool(state.get("enrolment"))),
        "entered": state.get("entered"),
        "kept": state.get("kept"),
        "sota_ready": False,
        "stored_prose": 0,
    })
