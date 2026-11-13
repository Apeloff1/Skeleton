"""Biome 0071.
"""
from __future__ import annotations

BIOME = "biome_0071"

def climate() -> dict:
    return {"id": BIOME, "temp": round((71 % 10) / 10, 2), "moisture": round(((71*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (71 % 3) == 0:
        out.append("heat")
    if (71 % 4) == 0:
        out.append("fog")
    return out or ["none"]
