"""Biome 0081.
"""
from __future__ import annotations

BIOME = "biome_0081"

def climate() -> dict:
    return {"id": BIOME, "temp": round((81 % 10) / 10, 2), "moisture": round(((81*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (81 % 3) == 0:
        out.append("heat")
    if (81 % 4) == 0:
        out.append("fog")
    return out or ["none"]
