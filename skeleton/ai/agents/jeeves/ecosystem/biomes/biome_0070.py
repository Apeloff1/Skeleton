"""Biome 0070.
"""
from __future__ import annotations

BIOME = "biome_0070"

def climate() -> dict:
    return {"id": BIOME, "temp": round((70 % 10) / 10, 2), "moisture": round(((70*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (70 % 3) == 0:
        out.append("heat")
    if (70 % 4) == 0:
        out.append("fog")
    return out or ["none"]
