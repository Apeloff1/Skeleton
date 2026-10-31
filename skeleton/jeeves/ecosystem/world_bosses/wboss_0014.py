"""World boss 0014.
"""
from __future__ import annotations

WBOSS = "wboss_0014"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 14 * 100, "window": 30}
