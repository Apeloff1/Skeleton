"""Advanced biome 0068.
"""
from __future__ import annotations

BIOME = "adv_biome_0068"

def climate() -> dict:
    return {"temp": round((68 % 20) / 20, 2), "moisture": round(((68*7) % 20) / 20, 2), "wind": round((68 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 68 % 3 == 0:
        base.append("ore")
    if 68 % 5 == 0:
        base.append("crystal")
    return base
