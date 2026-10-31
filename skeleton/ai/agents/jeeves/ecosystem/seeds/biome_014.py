"""Biome seed 014.
"""
from __future__ import annotations

BIOME_ID = "biome_014"
TEMPERATURE = round((14 % 10) / 10.0, 2)
MOISTURE = round(((14 * 3) % 10) / 10.0, 2)

def climate() -> dict:
    return {"id": BIOME_ID, "temp": TEMPERATURE, "moisture": MOISTURE}

def features() -> list[str]:
    base = ["ground", "sky"]
    if TEMPERATURE > 0.6:
        base.append("heat")
    if MOISTURE > 0.6:
        base.append("rain")
    return base
