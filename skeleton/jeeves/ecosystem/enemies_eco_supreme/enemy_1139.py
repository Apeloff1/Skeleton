"""Enemy eco_supreme 1139.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1139"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1139, "tier": 1139 % 5}

def apply(context: str = "") -> dict:
    if not context and 1139 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
