"""World boss 0016.
"""
from __future__ import annotations

WBOSS = "wboss_0016"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 16 * 100, "window": 30}
