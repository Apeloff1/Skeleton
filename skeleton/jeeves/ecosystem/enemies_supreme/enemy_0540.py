"""Enemy supreme 0540.
"""
from __future__ import annotations

ID = "enemy_supreme_0540"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 540, "tier": 540 % 5}

def apply(context: str = "") -> dict:
    if not context and 540 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
