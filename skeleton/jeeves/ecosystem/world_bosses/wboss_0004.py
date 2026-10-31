"""World boss 0004.
"""
from __future__ import annotations

WBOSS = "wboss_0004"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 4 * 100, "window": 30}
