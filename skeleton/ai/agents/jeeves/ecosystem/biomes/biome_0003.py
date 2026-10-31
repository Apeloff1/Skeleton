"""Biome 0003.
"""
from __future__ import annotations

BIOME = "biome_0003"

def climate() -> dict:
    return {"id": BIOME, "temp": round((3 % 10) / 10, 2), "moisture": round(((3*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (3 % 3) == 0:
        out.append("heat")
    if (3 % 4) == 0:
        out.append("fog")
    return out or ["none"]
