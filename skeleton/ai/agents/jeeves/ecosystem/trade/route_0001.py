"""Trade route 0001.
"""
from __future__ import annotations

ROUTE = "route_0001"

def profit(buy: float, sell: float) -> dict:
    return {"ok": True, "route": ROUTE, "margin": round(sell - buy, 2)}
