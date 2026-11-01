"""Enemy ultimate 0480.
"""
from __future__ import annotations

ID = "enemy_ultimate_0480"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 480, "tier": 480 % 5}

def apply(context: str = "") -> dict:
    if not context and 480 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
