"""Enemy eco_supreme 1064.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1064"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1064, "tier": 1064 % 5}

def apply(context: str = "") -> dict:
    if not context and 1064 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
