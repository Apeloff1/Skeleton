"""House 0023.
"""
from __future__ import annotations

HOUSE = "house_0023"

def furnish(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "house": HOUSE, "placed": item}
