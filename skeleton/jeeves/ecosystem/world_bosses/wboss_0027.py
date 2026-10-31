"""World boss 0027.
"""
from __future__ import annotations

WBOSS = "wboss_0027"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 27 * 100, "window": 30}
