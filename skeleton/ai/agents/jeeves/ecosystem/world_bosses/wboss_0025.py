"""World boss 0025.
"""
from __future__ import annotations

WBOSS = "wboss_0025"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 25 * 100, "window": 30}
