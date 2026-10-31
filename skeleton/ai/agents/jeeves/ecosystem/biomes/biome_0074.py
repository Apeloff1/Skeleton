"""Biome 0074.
"""
from __future__ import annotations

BIOME = "biome_0074"

def climate() -> dict:
    return {"id": BIOME, "temp": round((74 % 10) / 10, 2), "moisture": round(((74*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (74 % 3) == 0:
        out.append("heat")
    if (74 % 4) == 0:
        out.append("fog")
    return out or ["none"]
