"""Enemy ultimate 0462.
"""
from __future__ import annotations

ID = "enemy_ultimate_0462"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 462, "tier": 462 % 5}

def apply(context: str = "") -> dict:
    if not context and 462 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
