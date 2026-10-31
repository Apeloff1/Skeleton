"""Biome 0078.
"""
from __future__ import annotations

BIOME = "biome_0078"

def climate() -> dict:
    return {"id": BIOME, "temp": round((78 % 10) / 10, 2), "moisture": round(((78*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (78 % 3) == 0:
        out.append("heat")
    if (78 % 4) == 0:
        out.append("fog")
    return out or ["none"]
