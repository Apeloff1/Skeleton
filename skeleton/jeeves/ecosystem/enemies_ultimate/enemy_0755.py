"""Enemy ultimate 0755.
"""
from __future__ import annotations

ID = "enemy_ultimate_0755"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 755, "tier": 755 % 5}

def apply(context: str = "") -> dict:
    if not context and 755 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
