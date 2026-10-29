"""Sound event binder.
Maps gameplay events to audio cues for Godot emit.
"""
from __future__ import annotations
from typing import Any, Dict

SOUNDS = {
    "pack_clear": {"bus": "sfx", "pitch": 1.1, "volume": 0.7},
    "enemy_hit": {"bus": "sfx", "pitch": 0.9, "volume": 0.8},
    "boss_phase": {"bus": "music", "pitch": 1.0, "volume": 0.6},
    "salvage_spend": {"bus": "ui", "pitch": 1.2, "volume": 0.5},
    "extract": {"bus": "music", "pitch": 0.8, "volume": 0.9},
    "hazard": {"bus": "sfx", "pitch": 0.7, "volume": 0.6},
}

class SoundBinder:
    def for_event(self, event: str) -> Dict[str, Any]:
        return SOUNDS.get(event, SOUNDS["pack_clear"])
    def all_events(self) -> list:
        return list(SOUNDS.keys())
