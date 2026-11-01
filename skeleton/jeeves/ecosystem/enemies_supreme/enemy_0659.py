"""Enemy supreme 0659.
"""
from __future__ import annotations

ID = "enemy_supreme_0659"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 659, "tier": 659 % 5}

def apply(context: str = "") -> dict:
    if not context and 659 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
