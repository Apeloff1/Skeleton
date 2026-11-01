"""Enemy ultimate 0362.
"""
from __future__ import annotations

ID = "enemy_ultimate_0362"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 362, "tier": 362 % 5}

def apply(context: str = "") -> dict:
    if not context and 362 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
