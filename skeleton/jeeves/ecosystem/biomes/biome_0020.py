"""Biome 0020.
"""
from __future__ import annotations

BIOME = "biome_0020"

def climate() -> dict:
    return {"id": BIOME, "temp": round((20 % 10) / 10, 2), "moisture": round(((20*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (20 % 3) == 0:
        out.append("heat")
    if (20 % 4) == 0:
        out.append("fog")
    return out or ["none"]
