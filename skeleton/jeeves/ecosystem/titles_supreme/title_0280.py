"""Title supreme 0280.
"""
from __future__ import annotations

ID = "title_supreme_0280"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 280}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
