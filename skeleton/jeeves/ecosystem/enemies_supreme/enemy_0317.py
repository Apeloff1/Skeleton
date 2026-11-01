"""Enemy supreme 0317.
"""
from __future__ import annotations

ID = "enemy_supreme_0317"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 317, "tier": 317 % 5}

def apply(context: str = "") -> dict:
    if not context and 317 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
