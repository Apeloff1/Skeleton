"""Biome 0096.
"""
from __future__ import annotations

BIOME = "biome_0096"

def climate() -> dict:
    return {"id": BIOME, "temp": round((96 % 10) / 10, 2), "moisture": round(((96*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (96 % 3) == 0:
        out.append("heat")
    if (96 % 4) == 0:
        out.append("fog")
    return out or ["none"]
