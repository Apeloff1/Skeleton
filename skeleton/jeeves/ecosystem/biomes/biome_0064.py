"""Biome 0064.
"""
from __future__ import annotations

BIOME = "biome_0064"

def climate() -> dict:
    return {"id": BIOME, "temp": round((64 % 10) / 10, 2), "moisture": round(((64*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (64 % 3) == 0:
        out.append("heat")
    if (64 % 4) == 0:
        out.append("fog")
    return out or ["none"]
