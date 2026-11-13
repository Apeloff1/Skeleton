"""Trade route 0038.
"""
from __future__ import annotations

ROUTE = "route_0038"

def profit(buy: float, sell: float) -> dict:
    return {"ok": True, "route": ROUTE, "margin": round(sell - buy, 2)}
