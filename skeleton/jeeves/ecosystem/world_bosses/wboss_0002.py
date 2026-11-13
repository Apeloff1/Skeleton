"""World boss 0002.
"""
from __future__ import annotations

WBOSS = "wboss_0002"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 2 * 100, "window": 30}
