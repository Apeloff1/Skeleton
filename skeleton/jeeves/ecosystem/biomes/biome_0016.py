"""Biome 0016.
"""
from __future__ import annotations

BIOME = "biome_0016"

def climate() -> dict:
    return {"id": BIOME, "temp": round((16 % 10) / 10, 2), "moisture": round(((16*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (16 % 3) == 0:
        out.append("heat")
    if (16 % 4) == 0:
        out.append("fog")
    return out or ["none"]
