"""Rep max 0121.
"""
from __future__ import annotations

ID = "rep_max_0121"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 121}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
