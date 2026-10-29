"""Advanced biome 0091.
"""
from __future__ import annotations

BIOME = "adv_biome_0091"

def climate() -> dict:
    return {"temp": round((91 % 20) / 20, 2), "moisture": round(((91*7) % 20) / 20, 2), "wind": round((91 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 91 % 3 == 0:
        base.append("ore")
    if 91 % 5 == 0:
        base.append("crystal")
    return base
