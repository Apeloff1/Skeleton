"""Law pack index. Names only."""

from __future__ import annotations

from typing import Any


PACKS = (
    "status_laws", "status_laws2", "verb_pack", "encounter_pack", "quest_pack",
    "dialogue_pack", "craft_pack", "climate_pack", "skill_pack", "economy_pack",
    "door_pack", "tile_pack", "fog_pack", "save_pack", "shaft_pack", "agent_pack",
    "role_pack", "pressure_pack", "chronicle_pack", "hazard_pack", "hunt_field",
    "occupancy", "extract_ledger", "frame_log", "law_composer",
)


def census() -> dict[str, Any]:
    return {
        "kind": "law_census",
        "n": len(PACKS),
        "packs": list(PACKS),
        "sota_ready": False,
        "stored_prose": 0,
    }
