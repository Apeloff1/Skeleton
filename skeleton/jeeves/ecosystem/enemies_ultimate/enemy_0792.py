"""Enemy ultimate 0792.
"""
from __future__ import annotations

ID = "enemy_ultimate_0792"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 792, "tier": 792 % 5}

def apply(context: str = "") -> dict:
    if not context and 792 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
