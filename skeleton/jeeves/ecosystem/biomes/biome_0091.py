"""Biome 0091.
"""
from __future__ import annotations

BIOME = "biome_0091"

def climate() -> dict:
    return {"id": BIOME, "temp": round((91 % 10) / 10, 2), "moisture": round(((91*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (91 % 3) == 0:
        out.append("heat")
    if (91 % 4) == 0:
        out.append("fog")
    return out or ["none"]
