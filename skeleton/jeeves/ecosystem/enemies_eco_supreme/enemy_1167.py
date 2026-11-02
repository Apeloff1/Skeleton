"""Enemy eco_supreme 1167.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1167"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1167, "tier": 1167 % 5}

def apply(context: str = "") -> dict:
    if not context and 1167 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
