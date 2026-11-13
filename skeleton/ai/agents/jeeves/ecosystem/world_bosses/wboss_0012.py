"""World boss 0012.
"""
from __future__ import annotations

WBOSS = "wboss_0012"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 12 * 100, "window": 30}
