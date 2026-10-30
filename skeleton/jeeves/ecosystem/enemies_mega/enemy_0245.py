"""Enemy mega 0245.
"""
from __future__ import annotations

ID = "enemy_mega_0245"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 245, "tier": 245 % 5}

def apply(context: str = "") -> dict:
    if not context and 245 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
