"""Biome 0018.
"""
from __future__ import annotations

BIOME = "biome_0018"

def climate() -> dict:
    return {"id": BIOME, "temp": round((18 % 10) / 10, 2), "moisture": round(((18*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (18 % 3) == 0:
        out.append("heat")
    if (18 % 4) == 0:
        out.append("fog")
    return out or ["none"]
