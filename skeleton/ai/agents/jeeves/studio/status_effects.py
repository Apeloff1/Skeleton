"""Status effect system.
Applies timed buffs/debuffs from loot, combat, and optical events.
"""
from __future__ import annotations
from typing import Any, Dict, List

class StatusEffects:
    def __init__(self):
        self.active: List[Dict[str, Any]] = []
    def apply(self, name: str, duration: float, magnitude: float, source: str = "") -> None:
        self.active.append({"name": name, "duration": duration, "magnitude": magnitude, "source": source})
    def tick(self, dt: float) -> List[str]:
        expired = []
        for e in self.active:
            e["duration"] -= dt
            if e["duration"] <= 0:
                expired.append(e["name"])
        self.active = [e for e in self.active if e["duration"] > 0]
        return expired
    def modifiers(self) -> Dict[str, float]:
        speed = 1.0
        armor = 0.0
        dmg = 1.0
        for e in self.active:
            if e["name"] == "speed_boost":
                speed += e["magnitude"]
            elif e["name"] == "armor_up":
                armor += e["magnitude"]
            elif e["name"] == "dmg_up":
                dmg += e["magnitude"]
        return {"speed": speed, "armor": armor, "damage": dmg}
    def status(self) -> List[Dict[str, Any]]:
        return self.active
