"""Procedural event generator.
Spawns timed events from optical, difficulty, and room state.
"""
from __future__ import annotations
from typing import Any, Dict, List
import random

class EventGenerator:
    def __init__(self, seed: int = 8847291):
        self.rng = random.Random(seed)
    def next_events(self, optical: float, difficulty: float, rooms_cleared: int) -> List[Dict[str, Any]]:
        events = []
        if self.rng.random() < 0.3 + optical * 0.2:
            events.append({"type": "salvage_cache", "value": int(8 + difficulty * 6), "optical_tag": "pack"})
        if self.rng.random() < 0.2 + difficulty * 0.15:
            events.append({"type": "hazard_pulse", "damage": int(5 + difficulty * 4), "optical_tag": "hazard"})
        if rooms_cleared > 3 and self.rng.random() < 0.25:
            events.append({"type": "elite_spawn", "health": int(40 + difficulty * 20), "optical_tag": "enemy"})
        if optical > 0.92 and self.rng.random() < 0.15:
            events.append({"type": "optical_rift", "reward_mult": 1.5, "optical_tag": "special"})
        return events
