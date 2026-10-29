"""Advanced biome 0053.
"""
from __future__ import annotations

BIOME = "adv_biome_0053"

def climate() -> dict:
    return {"temp": round((53 % 20) / 20, 2), "moisture": round(((53*7) % 20) / 20, 2), "wind": round((53 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 53 % 3 == 0:
        base.append("ore")
    if 53 % 5 == 0:
        base.append("crystal")
    return base
