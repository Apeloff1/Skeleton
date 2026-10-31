"""Biome 0035.
"""
from __future__ import annotations

BIOME = "biome_0035"

def climate() -> dict:
    return {"id": BIOME, "temp": round((35 % 10) / 10, 2), "moisture": round(((35*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (35 % 3) == 0:
        out.append("heat")
    if (35 % 4) == 0:
        out.append("fog")
    return out or ["none"]
