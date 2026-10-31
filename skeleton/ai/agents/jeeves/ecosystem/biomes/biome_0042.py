"""Biome 0042.
"""
from __future__ import annotations

BIOME = "biome_0042"

def climate() -> dict:
    return {"id": BIOME, "temp": round((42 % 10) / 10, 2), "moisture": round(((42*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (42 % 3) == 0:
        out.append("heat")
    if (42 % 4) == 0:
        out.append("fog")
    return out or ["none"]
