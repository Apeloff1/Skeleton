"""Enemy supreme 0417.
"""
from __future__ import annotations

ID = "enemy_supreme_0417"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 417, "tier": 417 % 5}

def apply(context: str = "") -> dict:
    if not context and 417 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
