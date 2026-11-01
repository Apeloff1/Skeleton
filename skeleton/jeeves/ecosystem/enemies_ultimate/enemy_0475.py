"""Enemy ultimate 0475.
"""
from __future__ import annotations

ID = "enemy_ultimate_0475"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 475, "tier": 475 % 5}

def apply(context: str = "") -> dict:
    if not context and 475 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
