"""Biome 0007.
"""
from __future__ import annotations

BIOME = "biome_0007"

def climate() -> dict:
    return {"id": BIOME, "temp": round((7 % 10) / 10, 2), "moisture": round(((7*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (7 % 3) == 0:
        out.append("heat")
    if (7 % 4) == 0:
        out.append("fog")
    return out or ["none"]
