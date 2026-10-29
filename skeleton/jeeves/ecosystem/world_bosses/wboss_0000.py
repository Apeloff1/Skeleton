"""World boss 0000.
"""
from __future__ import annotations

WBOSS = "wboss_0000"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 0 * 100, "window": 30}
