"""Biome 0055.
"""
from __future__ import annotations

BIOME = "biome_0055"

def climate() -> dict:
    return {"id": BIOME, "temp": round((55 % 10) / 10, 2), "moisture": round(((55*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (55 % 3) == 0:
        out.append("heat")
    if (55 % 4) == 0:
        out.append("fog")
    return out or ["none"]
