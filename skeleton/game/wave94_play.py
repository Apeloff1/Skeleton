"""Wave-94 play. Ell, yard, perch, furlong."""

from __future__ import annotations

from typing import Any

from skeleton.game.ell_pack import measure as ell_m
from skeleton.game.furlong_pack import measure as fur_m
from skeleton.game.perch_pack import measure as perch_m
from skeleton.game.seal_card import seal
from skeleton.game.wave94_index import census
from skeleton.game.yardstick_pack import measure as yard_m


def play(*, seed: int = 8847291) -> dict[str, Any]:
    state = ell_m({}, "el_00", 2)
    state = yard_m(state, "yd_00", 3)
    state = perch_m(state, "pe_00", 1)
    state = fur_m(state, "fl_00", 1)
    info = census()
    return seal({
        "kind": "wave94_play",
        "seed": int(seed),
        "packs": info["n"],
        "len": state.get("len"),
        "yd": state.get("yd"),
        "fur": state.get("fur"),
        "sota_ready": False,
        "stored_prose": 0,
    })
