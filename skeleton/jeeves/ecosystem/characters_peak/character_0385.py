"""Character peak 0385.
"""
from __future__ import annotations

ID = "character_peak_0385"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 385, "tier": 385 % 5}

def apply(context: str = "") -> dict:
    if not context and 385 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
