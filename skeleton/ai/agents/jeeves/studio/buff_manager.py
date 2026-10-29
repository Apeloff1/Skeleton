"""Buff manager. Temporary positive modifiers."""
from typing import Any, Dict, List
class BuffManager:
    def __init__(self):
        self.buffs: List[Dict[str, Any]] = []
    def add(self, name: str, duration: float, mult: float) -> None:
        self.buffs.append({"name": name, "duration": duration, "mult": mult})
    def tick(self, dt: float) -> None:
        for b in self.buffs: b["duration"] -= dt
        self.buffs = [b for b in self.buffs if b["duration"] > 0]
