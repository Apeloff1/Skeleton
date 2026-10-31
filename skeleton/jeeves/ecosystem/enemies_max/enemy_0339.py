"""Enemy max 0339.
"""
from __future__ import annotations

ID = "enemy_max_0339"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 339, "tier": 339 % 5}

def apply(context: str = "") -> dict:
    if not context and 339 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
