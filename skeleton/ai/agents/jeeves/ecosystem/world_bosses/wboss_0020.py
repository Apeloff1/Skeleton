"""World boss 0020.
"""
from __future__ import annotations

WBOSS = "wboss_0020"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 20 * 100, "window": 30}
