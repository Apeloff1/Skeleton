"""Title ultimate 0287.
"""
from __future__ import annotations

ID = "title_ultimate_0287"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 287}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
