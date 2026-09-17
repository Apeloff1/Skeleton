"""Second wave-110 pass. Extra enrol + memorial."""

from __future__ import annotations

from typing import Any

from skeleton.game.enrolment_pack import enrol
from skeleton.game.memorial_pack import record
from skeleton.game.seal_card import seal


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = enrol({"enrolment": []}, "en_01")
    state = record(state, "mm_01")
    return seal({
        "kind": "wave110_more",
        "seed": int(seed),
        "enrolment": int(bool(state.get("enrolment"))),
        "kept": state.get("kept"),
        "sota_ready": False,
        "stored_prose": 0,
    })
