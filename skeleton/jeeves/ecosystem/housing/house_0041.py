"""House 0041.
"""
from __future__ import annotations

HOUSE = "house_0041"

def furnish(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "house": HOUSE, "placed": item}
