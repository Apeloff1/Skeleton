"""Rep max 0126.
"""
from __future__ import annotations

ID = "rep_max_0126"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 126}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
