"""World boss 0029.
"""
from __future__ import annotations

WBOSS = "wboss_0029"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 29 * 100, "window": 30}
