"""Enemy supreme 0399.
"""
from __future__ import annotations

ID = "enemy_supreme_0399"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 399, "tier": 399 % 5}

def apply(context: str = "") -> dict:
    if not context and 399 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
