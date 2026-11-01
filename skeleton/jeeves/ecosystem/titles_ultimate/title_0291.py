"""Title ultimate 0291.
"""
from __future__ import annotations

ID = "title_ultimate_0291"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 291}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
