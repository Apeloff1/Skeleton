"""World boss 0023.
"""
from __future__ import annotations

WBOSS = "wboss_0023"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 23 * 100, "window": 30}
