"""Enemy eco_supreme 0915.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0915"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 915, "tier": 915 % 5}

def apply(context: str = "") -> dict:
    if not context and 915 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
