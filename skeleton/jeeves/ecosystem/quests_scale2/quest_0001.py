"""Quest scale2 0001.
"""
from __future__ import annotations

ID = "quest_scale2_0001"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 1}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
