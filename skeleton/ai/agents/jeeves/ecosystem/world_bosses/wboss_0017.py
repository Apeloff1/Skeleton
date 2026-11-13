"""World boss 0017.
"""
from __future__ import annotations

WBOSS = "wboss_0017"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 17 * 100, "window": 30}
