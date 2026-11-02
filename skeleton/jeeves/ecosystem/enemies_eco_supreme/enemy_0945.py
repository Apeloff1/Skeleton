"""Enemy eco_supreme 0945.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0945"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 945, "tier": 945 % 5}

def apply(context: str = "") -> dict:
    if not context and 945 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
