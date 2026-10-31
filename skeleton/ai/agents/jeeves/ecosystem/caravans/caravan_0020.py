"""Caravan 0020.
"""
from __future__ import annotations

CARAVAN = "caravan_0020"

def depart(goods: list[str]) -> dict:
    if not goods:
        return {"ok": False, "reason": "empty"}
    return {"ok": True, "caravan": CARAVAN, "goods": goods[:8], "eta": 3}
