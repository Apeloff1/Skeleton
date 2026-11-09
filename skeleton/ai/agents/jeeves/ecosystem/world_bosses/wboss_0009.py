"""World boss 0009.
"""
from __future__ import annotations

WBOSS = "wboss_0009"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 9 * 100, "window": 30}
