"""Second wave-7 pass. Inspect, evidence, form, roster, tide."""

from __future__ import annotations

from typing import Any

from skeleton.game.evidence_pack import bag
from skeleton.game.form_pack import file
from skeleton.game.inspect_pack import run as inspect_run
from skeleton.game.roster_pack import add as roster_add
from skeleton.game.seal_card import seal
from skeleton.game.tide_pack import rise


def play(*, seed: int = 8847291, digest: str = "d") -> dict[str, Any]:
    state: dict[str, Any] = {"alert": 0, "evidence": {}, "form": {}, "roster": {}}
    state = inspect_run(state, "in_00")
    state = bag(state, "ev_00", digest or "d")
    state = file(state, "fm_00", digest or "d")
    state = roster_add(state, "rs_00", "player")
    node = rise({}, "td_00")
    return seal({
        "kind": "wave7_more",
        "seed": int(seed),
        "inspect": state.get("inspect"),
        "evidence": int(bool(state.get("evidence"))),
        "form": int(bool(state.get("form"))),
        "roster": int(bool(state.get("roster"))),
        "tide": node.get("tide"),
        "sota_ready": False,
        "stored_prose": 0,
    })
