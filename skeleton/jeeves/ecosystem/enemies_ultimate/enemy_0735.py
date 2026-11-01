"""Enemy ultimate 0735.
"""
from __future__ import annotations

ID = "enemy_ultimate_0735"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 735, "tier": 735 % 5}

def apply(context: str = "") -> dict:
    if not context and 735 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
