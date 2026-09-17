"""Wave-5 play. Noise + faction + clock + light + gate."""

from __future__ import annotations

from typing import Any

from skeleton.game.clock_pack import enter as clock_enter
from skeleton.game.faction_pack import stand
from skeleton.game.gate_pack import GatePackError, open_gate
from skeleton.game.light_pack import on as light_on
from skeleton.game.noise_map import emit as noise_emit
from skeleton.game.seal_card import seal
from skeleton.game.wave5_index import census
from skeleton.game.wound_pack import hit


def play(*, seed: int = 8847291) -> dict[str, Any]:
    node = noise_emit({"heat": 6, "loud": 0, "los_pen": 4}, "nz_00", 3)
    node = light_on(node, "lt_00")
    state: dict[str, Any] = {
        "heat": max(8, int(node.get("heat", 0))),
        "hp": 40,
        "extracted": 0,
        "faction": {},
        "wound": {},
    }
    state = stand(state, "ash", 2)
    state = clock_enter(state, "ph_00")
    state = hit(state, "arm_l", 1)
    extracted = 0
    try:
        state = open_gate(state, "gt_00")
        extracted = 1
    except GatePackError:
        extracted = int(state.get("extracted", 0))
    info = census()
    return seal({
        "kind": "wave5_play",
        "seed": int(seed),
        "packs": info["n"],
        "loud": node.get("loud"),
        "light": node.get("light"),
        "extract_count": extracted,
        "warp_count": int(state.get("warp_count", 0)),
        "sota_ready": False,
        "stored_prose": 0,
    })
