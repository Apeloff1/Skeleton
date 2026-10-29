"""Advanced biome 0007.
"""
from __future__ import annotations

BIOME = "adv_biome_0007"

def climate() -> dict:
    return {"temp": round((7 % 20) / 20, 2), "moisture": round(((7*7) % 20) / 20, 2), "wind": round((7 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 7 % 3 == 0:
        base.append("ore")
    if 7 % 5 == 0:
        base.append("crystal")
    return base
