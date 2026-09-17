"""Flesh sim. Floors + climate + encounter + barter + skills + extract once."""

from __future__ import annotations

from typing import Any

from skeleton.game.barter_book import apply_offer
from skeleton.game.climate import run as climate_run
from skeleton.game.dialogue_ptr import start as dlg_start
from skeleton.game.dialogue_ptr import step as dlg_step
from skeleton.game.encounters import run as enc_run
from skeleton.game.floors import weave_campus
from skeleton.game.quest_ptr import open_quest, tick_quest
from skeleton.game.save_slots import blank_bank, write
from skeleton.game.seal_card import seal
from skeleton.game.skills import learn


class FleshSimError(ValueError):
    pass


def play(*, seed: int = 8847291) -> dict[str, Any]:
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    climate = climate_run(campus["nodes"], ticks=12, phase="vent")
    enc = enc_run("extract_gate", int(seed), ["enter", "heat", "extract", "wait"])
    state: dict[str, Any] = {
        "heat": climate["peak"],
        "scrap": 4,
        "parts": 1,
        "xp": 12,
        "sleep": 8,
        "extracted": 0,
        "skills": [],
    }
    try:
        state = apply_offer(state, "scrap_for_parts")
    except Exception:
        pass
    try:
        state = learn(state, "heat_ward")
    except Exception:
        pass
    quest = open_quest("stoke_heat", int(seed))
    quest = tick_quest(quest, state)
    dlg = dlg_start("extract_ready")
    dlg = dlg_step(dlg, state)
    if climate["peak"] >= 8 and int(state.get("extracted", 0)) == 0:
        state["extracted"] = 1
        state["warp_count"] = 1
    body = {
        "kind": "flesh_sim",
        "seed": int(seed),
        "floors": campus["floors"],
        "nodes": len(campus["nodes"]),
        "shafts": campus["shafts"],
        "peak_heat": climate["peak"],
        "tokens": climate["tokens"],
        "enc": enc["enc"],
        "quest_done": quest.get("done"),
        "dialogue_node": dlg.get("node"),
        "skills": list(state.get("skills") or []),
        "extract_count": int(state.get("extracted", 0)),
        "warp_count": int(state.get("warp_count", 0)),
        "sota_ready": False,
        "stored_prose": 0,
    }
    sealed = seal(body)
    bank = write(blank_bank(), "slot0", sealed)
    sealed["saved"] = bool(bank.get("slot0"))
    return sealed
