"""Trade route 0000.
"""
from __future__ import annotations

ROUTE = "route_0000"

def profit(buy: float, sell: float) -> dict:
    return {"ok": True, "route": ROUTE, "margin": round(sell - buy, 2)}
