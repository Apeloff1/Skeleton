"""Wave-4 law index."""

from __future__ import annotations

from typing import Any


PACKS = (
    "weather_cells", "lock_patterns", "heat_sources", "patrol_routes", "craft_steps",
    "save_marks", "dialogue_beats", "status_wave", "verb_wave", "hazard_wave", "tile_wave",
    "quest_wave", "encounter_wave", "skill_wave", "agent_wave", "pressure_wave", "fog_wave",
    "offer_wave", "hit_wave", "dream_wave", "stance_wave", "chronicle_wave", "door_wave",
    "cell_wave", "buff_wave", "shaft_wave", "signal_wave", "pred_wave",
)


def census() -> dict[str, Any]:
    return {
        "kind": "wave4_census",
        "n": len(PACKS),
        "packs": list(PACKS),
        "sota_ready": False,
        "stored_prose": 0,
    }
