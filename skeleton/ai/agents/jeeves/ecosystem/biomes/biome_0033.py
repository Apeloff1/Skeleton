"""Biome 0033.
"""
from __future__ import annotations

BIOME = "biome_0033"

def climate() -> dict:
    return {"id": BIOME, "temp": round((33 % 10) / 10, 2), "moisture": round(((33*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (33 % 3) == 0:
        out.append("heat")
    if (33 % 4) == 0:
        out.append("fog")
    return out or ["none"]
