"""Enemy ultimate 0721.
"""
from __future__ import annotations

ID = "enemy_ultimate_0721"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 721, "tier": 721 % 5}

def apply(context: str = "") -> dict:
    if not context and 721 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
