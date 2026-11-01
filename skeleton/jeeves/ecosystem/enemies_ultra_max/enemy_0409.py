"""Enemy ultra_max 0409.
"""
from __future__ import annotations

ID = "enemy_ultra_max_0409"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 409, "tier": 409 % 5}

def apply(context: str = "") -> dict:
    if not context and 409 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
