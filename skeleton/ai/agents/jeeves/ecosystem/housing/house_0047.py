"""House 0047.
"""
from __future__ import annotations

HOUSE = "house_0047"

def furnish(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "house": HOUSE, "placed": item}
