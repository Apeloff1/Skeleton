"""Enemy eco_supreme 0954.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0954"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 954, "tier": 954 % 5}

def apply(context: str = "") -> dict:
    if not context and 954 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
