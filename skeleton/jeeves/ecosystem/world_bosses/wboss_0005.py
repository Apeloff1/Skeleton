"""World boss 0005.
"""
from __future__ import annotations

WBOSS = "wboss_0005"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 5 * 100, "window": 30}
