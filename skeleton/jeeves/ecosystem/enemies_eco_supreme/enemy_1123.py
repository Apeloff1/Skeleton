"""Enemy eco_supreme 1123.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1123"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1123, "tier": 1123 % 5}

def apply(context: str = "") -> dict:
    if not context and 1123 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
