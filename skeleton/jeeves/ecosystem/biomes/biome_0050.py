"""Biome 0050.
"""
from __future__ import annotations

BIOME = "biome_0050"

def climate() -> dict:
    return {"id": BIOME, "temp": round((50 % 10) / 10, 2), "moisture": round(((50*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (50 % 3) == 0:
        out.append("heat")
    if (50 % 4) == 0:
        out.append("fog")
    return out or ["none"]
