"""Biome 0053.
"""
from __future__ import annotations

BIOME = "biome_0053"

def climate() -> dict:
    return {"id": BIOME, "temp": round((53 % 10) / 10, 2), "moisture": round(((53*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (53 % 3) == 0:
        out.append("heat")
    if (53 % 4) == 0:
        out.append("fog")
    return out or ["none"]
