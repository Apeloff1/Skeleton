"""Earned quest milestones derived from verified runtime state, never client-claimed."""
from __future__ import annotations
from .schema import World

def progress(world: World, state: dict) -> dict:
    events = state["events"]
    rescued = sum(value == "rescued" for value in state["civilians"].values())
    total = len(world.civilians)
    collected = sum(event.startswith("gather:") for event in events)
    crafted = sum(event.startswith("craft:") for event in events)
    defeated = sum(enemy["health"] == 0 for enemy in state["raiders"].values())
    quests = {
        "first_supply": collected >= 1,
        "field_crafting": crafted >= 1,
        "first_rescue": rescued >= 1,
        "all_rescued": rescued == total,
        "reach_shelter": tuple(state["position"]) == world.shelter,
        "beacon_lit": state["flags"]["beacon"],
        "ridges_secured": defeated == len(world.raiders),
        "protect_ending": state["status"] == "won:protect",
        "salvage_ending": state["status"] == "won:salvage",
    }
    return {
        "schema": "ridge.rescue.quests.v1",
        "turn": state["turn"], "earned": quests,
        "civilians_rescued": rescued, "civilians_total": total,
        "supplies_collected": collected, "items_crafted": crafted,
        "raiders_defeated": defeated, "raiders_total": len(world.raiders),
        "ending": state["status"] if state["status"].startswith("won:") else None,
    }
