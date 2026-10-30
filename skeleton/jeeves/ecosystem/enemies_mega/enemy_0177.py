"""Enemy mega 0177.
"""
from __future__ import annotations

ID = "enemy_mega_0177"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 177, "tier": 177 % 5}

def apply(context: str = "") -> dict:
    if not context and 177 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
