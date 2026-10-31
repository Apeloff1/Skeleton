"""Enemy max 0185.
"""
from __future__ import annotations

ID = "enemy_max_0185"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 185, "tier": 185 % 5}

def apply(context: str = "") -> dict:
    if not context and 185 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
