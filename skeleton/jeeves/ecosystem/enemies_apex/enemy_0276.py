"""Enemy apex 0276.
"""
from __future__ import annotations

ID = "enemy_apex_0276"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 276, "tier": 276 % 5}

def apply(context: str = "") -> dict:
    if not context and 276 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
