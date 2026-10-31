"""World boss 0018.
"""
from __future__ import annotations

WBOSS = "wboss_0018"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 18 * 100, "window": 30}
