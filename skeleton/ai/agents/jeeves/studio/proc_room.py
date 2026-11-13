"""Procedural room.
Optical-density room with biome and loot.
"""
from typing import Any, Dict

class ProcRoom:
    def generate(self, biome: str, optical: float) -> Dict[str, Any]:
        if not isinstance(biome, str) or not biome.strip():
            return {"ok": False, "reason": "empty_biome", "schema": "skeleton.proc.room.v1"}
        density = round(0.5 + optical*0.5, 2)
        return {"ok": True, "biome": biome, "optical": optical, "density": density, "loot": int(density*5), "reason": "ok", "schema": "skeleton.proc.room.v1"}
