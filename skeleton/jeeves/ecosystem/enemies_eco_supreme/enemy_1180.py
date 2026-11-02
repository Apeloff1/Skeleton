"""Enemy eco_supreme 1180.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1180"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1180, "tier": 1180 % 5}

def apply(context: str = "") -> dict:
    if not context and 1180 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
