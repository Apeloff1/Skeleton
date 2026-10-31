"""Biome 0086.
"""
from __future__ import annotations

BIOME = "biome_0086"

def climate() -> dict:
    return {"id": BIOME, "temp": round((86 % 10) / 10, 2), "moisture": round(((86*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (86 % 3) == 0:
        out.append("heat")
    if (86 % 4) == 0:
        out.append("fog")
    return out or ["none"]
