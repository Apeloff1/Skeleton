"""World boss 0001.
"""
from __future__ import annotations

WBOSS = "wboss_0001"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 1 * 100, "window": 30}
