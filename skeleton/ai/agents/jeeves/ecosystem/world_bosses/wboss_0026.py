"""World boss 0026.
"""
from __future__ import annotations

WBOSS = "wboss_0026"

def spawn() -> dict:
    return {"ok": True, "wboss": WBOSS, "hp": 5000 + 26 * 100, "window": 30}
