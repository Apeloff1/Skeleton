"""Biome 0082.
"""
from __future__ import annotations

BIOME = "biome_0082"

def climate() -> dict:
    return {"id": BIOME, "temp": round((82 % 10) / 10, 2), "moisture": round(((82*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (82 % 3) == 0:
        out.append("heat")
    if (82 % 4) == 0:
        out.append("fog")
    return out or ["none"]
