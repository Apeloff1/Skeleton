"""Rep max 0134.
"""
from __future__ import annotations

ID = "rep_max_0134"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 134}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
