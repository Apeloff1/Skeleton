"""Enemy ultimate 0759.
"""
from __future__ import annotations

ID = "enemy_ultimate_0759"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 759, "tier": 759 % 5}

def apply(context: str = "") -> dict:
    if not context and 759 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
