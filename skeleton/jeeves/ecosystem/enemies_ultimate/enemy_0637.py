"""Enemy ultimate 0637.
"""
from __future__ import annotations

ID = "enemy_ultimate_0637"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 637, "tier": 637 % 5}

def apply(context: str = "") -> dict:
    if not context and 637 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
