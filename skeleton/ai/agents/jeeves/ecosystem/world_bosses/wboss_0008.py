"""World boss 0008.
"""
from __future__ import annotations

WBOSS = "wboss_0008"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 8 * 100, "window": 30}
