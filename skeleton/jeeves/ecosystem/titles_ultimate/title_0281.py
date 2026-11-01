"""Title ultimate 0281.
"""
from __future__ import annotations

ID = "title_ultimate_0281"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 281}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
