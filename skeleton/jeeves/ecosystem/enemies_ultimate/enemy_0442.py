"""Enemy ultimate 0442.
"""
from __future__ import annotations

ID = "enemy_ultimate_0442"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 442, "tier": 442 % 5}

def apply(context: str = "") -> dict:
    if not context and 442 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
