"""Enemy eco_supreme 0944.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0944"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 944, "tier": 944 % 5}

def apply(context: str = "") -> dict:
    if not context and 944 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
