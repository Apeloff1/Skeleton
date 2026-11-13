"""Biome 0027.
"""
from __future__ import annotations

BIOME = "biome_0027"

def climate() -> dict:
    return {"id": BIOME, "temp": round((27 % 10) / 10, 2), "moisture": round(((27*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (27 % 3) == 0:
        out.append("heat")
    if (27 % 4) == 0:
        out.append("fog")
    return out or ["none"]
