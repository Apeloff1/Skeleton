"""Effect catalog (creative).
Particle, camera shake, optical flash, salvage glow bindings.
"""
from __future__ import annotations
from typing import Any, Dict, List

EFFECTS = [
    {"id": "salvage_glow", "type": "particle", "color": "#88ffaa", "duration": 0.6},
    {"id": "boss_phase", "type": "camera_shake", "intensity": 0.4, "duration": 0.8},
    {"id": "optical_flash", "type": "screen", "color": "#ffffff", "duration": 0.15},
    {"id": "hazard_pulse", "type": "particle", "color": "#ff4444", "duration": 1.2},
    {"id": "extract_beam", "type": "beam", "color": "#44aaff", "duration": 2.0},
]

class EffectBinder:
    def for_event(self, event: str) -> Dict[str, Any]:
        mapping = {
            "pack_clear": "salvage_glow",
            "boss_phase": "boss_phase",
            "optical_spike": "optical_flash",
            "hazard": "hazard_pulse",
            "ending": "extract_beam",
        }
        eid = mapping.get(event, "salvage_glow")
        return next((e for e in EFFECTS if e["id"] == eid), EFFECTS[0])
