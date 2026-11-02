"""Enemy eco_supreme 1062.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1062"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1062, "tier": 1062 % 5}

def apply(context: str = "") -> dict:
    if not context and 1062 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
