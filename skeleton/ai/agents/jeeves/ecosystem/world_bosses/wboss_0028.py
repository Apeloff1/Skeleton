"""World boss 0028.
"""
from __future__ import annotations

WBOSS = "wboss_0028"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 28 * 100, "window": 30}
