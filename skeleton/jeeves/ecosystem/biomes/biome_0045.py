"""Biome 0045.
"""
from __future__ import annotations

BIOME = "biome_0045"

def climate() -> dict:
    return {"id": BIOME, "temp": round((45 % 10) / 10, 2), "moisture": round(((45*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (45 % 3) == 0:
        out.append("heat")
    if (45 % 4) == 0:
        out.append("fog")
    return out or ["none"]
