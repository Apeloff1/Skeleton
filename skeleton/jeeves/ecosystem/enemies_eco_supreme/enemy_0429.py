"""Enemy eco_supreme 0429.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0429"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 429, "tier": 429 % 5}

def apply(context: str = "") -> dict:
    if not context and 429 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
