"""Biome 0075.
"""
from __future__ import annotations

BIOME = "biome_0075"

def climate() -> dict:
    return {"id": BIOME, "temp": round((75 % 10) / 10, 2), "moisture": round(((75*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (75 % 3) == 0:
        out.append("heat")
    if (75 % 4) == 0:
        out.append("fog")
    return out or ["none"]
