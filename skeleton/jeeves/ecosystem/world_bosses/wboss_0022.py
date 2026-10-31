"""World boss 0022.
"""
from __future__ import annotations

WBOSS = "wboss_0022"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 22 * 100, "window": 30}
