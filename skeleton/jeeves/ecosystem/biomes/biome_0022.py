"""Biome 0022.
"""
from __future__ import annotations

BIOME = "biome_0022"

def climate() -> dict:
    return {"id": BIOME, "temp": round((22 % 10) / 10, 2), "moisture": round(((22*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (22 % 3) == 0:
        out.append("heat")
    if (22 % 4) == 0:
        out.append("fog")
    return out or ["none"]
