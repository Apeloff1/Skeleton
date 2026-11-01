"""Enemy ultimate 0648.
"""
from __future__ import annotations

ID = "enemy_ultimate_0648"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 648, "tier": 648 % 5}

def apply(context: str = "") -> dict:
    if not context and 648 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
