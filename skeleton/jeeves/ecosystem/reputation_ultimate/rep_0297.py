"""Rep ultimate 0297.
"""
from __future__ import annotations

ID = "rep_ultimate_0297"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 297}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
