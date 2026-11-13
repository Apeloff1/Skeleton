"""World boss 0003.
"""
from __future__ import annotations

WBOSS = "wboss_0003"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 3 * 100, "window": 30}
