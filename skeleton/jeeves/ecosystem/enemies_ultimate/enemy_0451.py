"""Enemy ultimate 0451.
"""
from __future__ import annotations

ID = "enemy_ultimate_0451"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 451, "tier": 451 % 5}

def apply(context: str = "") -> dict:
    if not context and 451 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
