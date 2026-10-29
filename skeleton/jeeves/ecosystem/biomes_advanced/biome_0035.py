"""Advanced biome 0035.
"""
from __future__ import annotations

BIOME = "adv_biome_0035"

def climate() -> dict:
    return {"temp": round((35 % 20) / 20, 2), "moisture": round(((35*7) % 20) / 20, 2), "wind": round((35 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 35 % 3 == 0:
        base.append("ore")
    if 35 % 5 == 0:
        base.append("crystal")
    return base
