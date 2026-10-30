"""Enemy mega 0045.
"""
from __future__ import annotations

ID = "enemy_mega_0045"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 45, "tier": 45 % 5}

def apply(context: str = "") -> dict:
    if not context and 45 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
