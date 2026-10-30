"""Supply line 0028.
"""
from __future__ import annotations

SUPPLY = "supply_0028"

def deliver(goods: int, distance: float) -> dict:
    if goods < 0 or distance < 0:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "supply": SUPPLY, "goods": goods, "eta": round(distance / 10, 2)}
