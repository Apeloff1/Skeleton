"""Title supreme 0173.
"""
from __future__ import annotations

ID = "title_supreme_0173"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 173}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
