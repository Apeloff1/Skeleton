"""Enemy eco_supreme 0379.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0379"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 379, "tier": 379 % 5}

def apply(context: str = "") -> dict:
    if not context and 379 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
