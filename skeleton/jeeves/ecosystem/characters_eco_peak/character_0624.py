"""Character eco_peak 0624.
"""
from __future__ import annotations

ID = "character_eco_peak_0624"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 624, "tier": 624 % 5}

def apply(context: str = "") -> dict:
    if not context and 624 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
