"""Mod loader.
Registers and applies optional modifiers to optical, salvage, and difficulty.
"""
from __future__ import annotations
from typing import Any, Dict, List

class ModLoader:
    def __init__(self):
        self.mods: List[Dict[str, Any]] = []
    def register(self, name: str, optical_mult: float = 1.0, salvage_mult: float = 1.0, difficulty_mult: float = 1.0) -> None:
        self.mods.append({"name": name, "optical_mult": optical_mult, "salvage_mult": salvage_mult, "difficulty_mult": difficulty_mult})
    def apply(self, optical: float, salvage: int, difficulty: float) -> Dict[str, Any]:
        o, s, d = optical, salvage, difficulty
        for m in self.mods:
            o *= m["optical_mult"]
            s = int(s * m["salvage_mult"])
            d *= m["difficulty_mult"]
        return {"optical": round(min(1.0, o), 3), "salvage": s, "difficulty": round(d, 2), "active": len(self.mods)}
