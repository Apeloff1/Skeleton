"""Enemy supreme 0565.
"""
from __future__ import annotations

ID = "enemy_supreme_0565"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 565, "tier": 565 % 5}

def apply(context: str = "") -> dict:
    if not context and 565 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
