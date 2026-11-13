"""World boss 0007.
"""
from __future__ import annotations

WBOSS = "wboss_0007"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 7 * 100, "window": 30}
