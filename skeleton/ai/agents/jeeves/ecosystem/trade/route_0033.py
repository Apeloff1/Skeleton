"""Trade route 0033.
"""
from __future__ import annotations

ROUTE = "route_0033"

def profit(buy: float, sell: float) -> dict:
    return {"ok": True, "route": ROUTE, "margin": round(sell - buy, 2)}
