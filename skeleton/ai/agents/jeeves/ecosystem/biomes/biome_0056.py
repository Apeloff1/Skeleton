"""Biome 0056.
"""
from __future__ import annotations

BIOME = "biome_0056"

def climate() -> dict:
    return {"id": BIOME, "temp": round((56 % 10) / 10, 2), "moisture": round(((56*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (56 % 3) == 0:
        out.append("heat")
    if (56 % 4) == 0:
        out.append("fog")
    return out or ["none"]
