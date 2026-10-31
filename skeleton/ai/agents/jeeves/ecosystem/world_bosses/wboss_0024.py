"""World boss 0024.
"""
from __future__ import annotations

WBOSS = "wboss_0024"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 24 * 100, "window": 30}
