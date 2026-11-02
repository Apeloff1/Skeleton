"""Enemy eco_supreme 1141.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1141"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1141, "tier": 1141 % 5}

def apply(context: str = "") -> dict:
    if not context and 1141 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
