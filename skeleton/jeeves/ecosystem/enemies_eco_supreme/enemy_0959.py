"""Enemy eco_supreme 0959.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0959"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 959, "tier": 959 % 5}

def apply(context: str = "") -> dict:
    if not context and 959 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
