"""Trade route 0006.
"""
from __future__ import annotations

ROUTE = "route_0006"

def profit(buy: float, sell: float) -> dict:
    return {"ok": True, "route": ROUTE, "margin": round(sell - buy, 2)}
