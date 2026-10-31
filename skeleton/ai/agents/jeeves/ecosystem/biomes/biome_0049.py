"""Biome 0049.
"""
from __future__ import annotations

BIOME = "biome_0049"

def climate() -> dict:
    return {"id": BIOME, "temp": round((49 % 10) / 10, 2), "moisture": round(((49*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (49 % 3) == 0:
        out.append("heat")
    if (49 % 4) == 0:
        out.append("fog")
    return out or ["none"]
