"""World boss 0013.
"""
from __future__ import annotations

WBOSS = "wboss_0013"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 13 * 100, "window": 30}
