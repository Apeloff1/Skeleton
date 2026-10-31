"""Biome 0084.
"""
from __future__ import annotations

BIOME = "biome_0084"

def climate() -> dict:
    return {"id": BIOME, "temp": round((84 % 10) / 10, 2), "moisture": round(((84*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (84 % 3) == 0:
        out.append("heat")
    if (84 % 4) == 0:
        out.append("fog")
    return out or ["none"]
