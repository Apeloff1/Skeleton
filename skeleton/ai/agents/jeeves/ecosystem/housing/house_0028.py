"""House 0028.
"""
from __future__ import annotations

HOUSE = "house_0028"

def furnish(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "house": HOUSE, "placed": item}
