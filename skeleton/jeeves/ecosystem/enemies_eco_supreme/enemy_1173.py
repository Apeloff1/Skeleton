"""Enemy eco_supreme 1173.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1173"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1173, "tier": 1173 % 5}

def apply(context: str = "") -> dict:
    if not context and 1173 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
