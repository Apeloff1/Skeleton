"""Biome 0048.
"""
from __future__ import annotations

BIOME = "biome_0048"

def climate() -> dict:
    return {"id": BIOME, "temp": round((48 % 10) / 10, 2), "moisture": round(((48*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (48 % 3) == 0:
        out.append("heat")
    if (48 % 4) == 0:
        out.append("fog")
    return out or ["none"]
