"""House 0005.
"""
from __future__ import annotations

HOUSE = "house_0005"

def furnish(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "house": HOUSE, "placed": item}
