"""Economy table 014.
"""
from __future__ import annotations

TABLE = "econ_014"

def price(base: float, optical: float = 0.9) -> float:
    if base < 0:
        return 0.0
    return round(base * (0.8 + optical * 0.4), 2)

def stock(item: str) -> dict:
    if not item:
        return {"ok": False, "reason": "no_item"}
    return {"ok": True, "table": TABLE, "item": item, "qty": 1 + (14 % 5)}
