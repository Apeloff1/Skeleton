"""Advanced biome 0082.
"""
from __future__ import annotations

BIOME = "adv_biome_0082"

def climate() -> dict:
    return {"temp": round((82 % 20) / 20, 2), "moisture": round(((82*7) % 20) / 20, 2), "wind": round((82 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 82 % 3 == 0:
        base.append("ore")
    if 82 % 5 == 0:
        base.append("crystal")
    return base
