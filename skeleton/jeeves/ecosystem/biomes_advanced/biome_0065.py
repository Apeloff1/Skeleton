"""Advanced biome 0065.
"""
from __future__ import annotations

BIOME = "adv_biome_0065"

def climate() -> dict:
    return {"temp": round((65 % 20) / 20, 2), "moisture": round(((65*7) % 20) / 20, 2), "wind": round((65 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 65 % 3 == 0:
        base.append("ore")
    if 65 % 5 == 0:
        base.append("crystal")
    return base
