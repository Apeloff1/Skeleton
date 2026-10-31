"""Biome 0069.
"""
from __future__ import annotations

BIOME = "biome_0069"

def climate() -> dict:
    return {"id": BIOME, "temp": round((69 % 10) / 10, 2), "moisture": round(((69*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (69 % 3) == 0:
        out.append("heat")
    if (69 % 4) == 0:
        out.append("fog")
    return out or ["none"]
