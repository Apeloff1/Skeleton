"""World boss 0011.
"""
from __future__ import annotations

WBOSS = "wboss_0011"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 11 * 100, "window": 30}
