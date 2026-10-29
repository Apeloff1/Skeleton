"""World boss 0010.
"""
from __future__ import annotations

WBOSS = "wboss_0010"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 10 * 100, "window": 30}
