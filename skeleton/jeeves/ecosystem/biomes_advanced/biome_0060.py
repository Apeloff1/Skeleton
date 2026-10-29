"""Advanced biome 0060.
"""
from __future__ import annotations

BIOME = "adv_biome_0060"

def climate() -> dict:
    return {"temp": round((60 % 20) / 20, 2), "moisture": round(((60*7) % 20) / 20, 2), "wind": round((60 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 60 % 3 == 0:
        base.append("ore")
    if 60 % 5 == 0:
        base.append("crystal")
    return base
