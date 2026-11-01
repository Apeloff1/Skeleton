"""Enemy ultimate 0418.
"""
from __future__ import annotations

ID = "enemy_ultimate_0418"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 418, "tier": 418 % 5}

def apply(context: str = "") -> dict:
    if not context and 418 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
