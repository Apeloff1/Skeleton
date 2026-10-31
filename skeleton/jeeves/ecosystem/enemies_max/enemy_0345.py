"""Enemy max 0345.
"""
from __future__ import annotations

ID = "enemy_max_0345"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 345, "tier": 345 % 5}

def apply(context: str = "") -> dict:
    if not context and 345 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
