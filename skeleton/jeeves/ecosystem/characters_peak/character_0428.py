"""Character peak 0428.
"""
from __future__ import annotations

ID = "character_peak_0428"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 428, "tier": 428 % 5}

def apply(context: str = "") -> dict:
    if not context and 428 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
