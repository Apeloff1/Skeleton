"""Trade route 0032.
"""
from __future__ import annotations

ROUTE = "route_0032"

def profit(buy: float, sell: float) -> dict:
    return {"ok": True, "route": ROUTE, "margin": round(sell - buy, 2)}
