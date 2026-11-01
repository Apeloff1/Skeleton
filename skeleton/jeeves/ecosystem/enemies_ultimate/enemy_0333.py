"""Enemy ultimate 0333.
"""
from __future__ import annotations

ID = "enemy_ultimate_0333"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 333, "tier": 333 % 5}

def apply(context: str = "") -> dict:
    if not context and 333 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
