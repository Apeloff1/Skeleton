"""World boss 0006.
"""
from __future__ import annotations

WBOSS = "wboss_0006"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 6 * 100, "window": 30}
