"""Debuff manager. Temporary negative modifiers."""
from typing import Any, Dict, List
class DebuffManager:
    def __init__(self):
        self.debuffs: List[Dict[str, Any]] = []
    def add(self, name: str, duration: float, mult: float) -> None:
        self.debuffs.append({"name": name, "duration": duration, "mult": mult})
    def tick(self, dt: float) -> None:
        for d in self.debuffs: d["duration"] -= dt
        self.debuffs = [d for d in self.debuffs if d["duration"] > 0]
