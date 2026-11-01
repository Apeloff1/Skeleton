"""Rep ultimate 0250.
"""
from __future__ import annotations

ID = "rep_ultimate_0250"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 250}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
