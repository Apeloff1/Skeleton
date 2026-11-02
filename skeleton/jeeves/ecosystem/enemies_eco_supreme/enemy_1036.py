"""Enemy eco_supreme 1036.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1036"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1036, "tier": 1036 % 5}

def apply(context: str = "") -> dict:
    if not context and 1036 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
