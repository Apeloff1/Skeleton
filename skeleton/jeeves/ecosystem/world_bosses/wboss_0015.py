"""World boss 0015.
"""
from __future__ import annotations

WBOSS = "wboss_0015"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 15 * 100, "window": 30}
