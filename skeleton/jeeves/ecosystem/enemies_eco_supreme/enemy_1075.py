"""Enemy eco_supreme 1075.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1075"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1075, "tier": 1075 % 5}

def apply(context: str = "") -> dict:
    if not context and 1075 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
