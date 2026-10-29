"""World boss 0019.
"""
from __future__ import annotations

WBOSS = "wboss_0019"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 19 * 100, "window": 30}
