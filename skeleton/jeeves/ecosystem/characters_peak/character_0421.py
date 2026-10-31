"""Character peak 0421.
"""
from __future__ import annotations

ID = "character_peak_0421"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 421, "tier": 421 % 5}

def apply(context: str = "") -> dict:
    if not context and 421 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
