"""Enemy ultimate 0669.
"""
from __future__ import annotations

ID = "enemy_ultimate_0669"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 669, "tier": 669 % 5}

def apply(context: str = "") -> dict:
    if not context and 669 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
