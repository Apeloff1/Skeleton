"""Enemy eco_supreme 0776.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0776"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 776, "tier": 776 % 5}

def apply(context: str = "") -> dict:
    if not context and 776 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
