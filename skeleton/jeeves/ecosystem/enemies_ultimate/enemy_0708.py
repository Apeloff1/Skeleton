"""Enemy ultimate 0708.
"""
from __future__ import annotations

ID = "enemy_ultimate_0708"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 708, "tier": 708 % 5}

def apply(context: str = "") -> dict:
    if not context and 708 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
