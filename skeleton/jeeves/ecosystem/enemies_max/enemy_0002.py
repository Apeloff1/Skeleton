"""Enemy max 0002.
"""
from __future__ import annotations

ID = "enemy_max_0002"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 2, "tier": 2 % 5}

def apply(context: str = "") -> dict:
    if not context and 2 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
