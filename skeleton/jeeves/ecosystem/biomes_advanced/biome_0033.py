"""Advanced biome 0033.
"""
from __future__ import annotations

BIOME = "adv_biome_0033"

def climate() -> dict:
    return {"temp": round((33 % 20) / 20, 2), "moisture": round(((33*7) % 20) / 20, 2), "wind": round((33 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 33 % 3 == 0:
        base.append("ore")
    if 33 % 5 == 0:
        base.append("crystal")
    return base
