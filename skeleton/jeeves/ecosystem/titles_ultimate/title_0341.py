"""Title ultimate 0341.
"""
from __future__ import annotations

ID = "title_ultimate_0341"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 341}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
