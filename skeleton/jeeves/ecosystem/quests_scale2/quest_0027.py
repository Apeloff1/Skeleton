"""Quest scale2 0027.
"""
from __future__ import annotations

ID = "quest_scale2_0027"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 27}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
