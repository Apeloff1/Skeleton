"""Biome 0038.
"""
from __future__ import annotations

BIOME = "biome_0038"

def climate() -> dict:
    return {"id": BIOME, "temp": round((38 % 10) / 10, 2), "moisture": round(((38*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (38 % 3) == 0:
        out.append("heat")
    if (38 % 4) == 0:
        out.append("fog")
    return out or ["none"]
