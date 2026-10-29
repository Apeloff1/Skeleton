"""World boss 0021.
"""
from __future__ import annotations

WBOSS = "wboss_0021"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 21 * 100, "window": 30}
